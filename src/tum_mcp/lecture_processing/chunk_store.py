"""Atomic chunk checkpoints keyed by verified audio, timing, source and model profile."""

import hashlib
import json
from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.runtime import MODELS, profile
from tum_mcp.lecture_processing.transcript_models import AudioQuality, Passage
from tum_mcp.lecture_processing.transcription import analyze, passages, recognize, uncertainty
from tum_mcp.lecture_processing.validity import Validity, require_content
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen
from tum_mcp.study_store import confined


class Chunk(Frozen):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    interval: Interval
    quality: AudioQuality
    language: str
    model: str
    passages: tuple[Passage, ...] = Field(max_length=5000)
    issues: tuple[str, ...] = ()

    @model_validator(mode="after")
    def bounded(self) -> "Chunk":
        if any(
            not self.interval.start_s
            <= passage.interval.start_s
            < passage.interval.end_s
            <= self.interval.end_s
            for passage in self.passages
        ):
            raise ValueError("Cached passages must remain inside their verified chunk.")
        return self


def process_chunk(
    audio: Path,
    span: Interval,
    validity: Validity,
    directory: Path,
    source_revision: str,
    *,
    language: str = "",
) -> tuple[Chunk, bool]:
    require_content(validity)
    if not any(
        item.start_s <= span.start_s < span.end_s <= item.end_s for item in validity.eligible
    ):
        raise CampusError(Code.SCOPE_DENIED, "Recognition chunk crosses excluded recording time.")
    if audio.is_symlink() or audio.stat().st_size > 320 * 1024**2:
        raise CampusError(Code.INVALID_RESPONSE, "Recognition requires bounded private PCM.")
    with audio.open("rb") as stream:
        audio_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                source_revision,
                audio_hash,
                span.model_dump(),
                profile(),
                MODELS,
                language,
                "pcm-v1-greedy-word-timing",
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = confined(directory, f"{fingerprint}.json")
    if path.is_file():
        if path.stat().st_size > 8 * 1024**2:
            raise CampusError(Code.INVALID_RESPONSE, "Recognition checkpoint exceeds its bound.")
        try:
            previous = Chunk.model_validate_json(path.read_bytes())
            if previous.fingerprint == fingerprint and previous.interval == span:
                return previous, True
        except ValidationError:
            raise CampusError(
                Code.INVALID_RESPONSE, "Recognition checkpoint is corrupt; preserve and inspect it."
            ) from None
    quality = analyze(audio)
    result = recognize(audio, quality.selected.channel, language=language)
    issues = uncertainty(result, language)
    selected = "base"
    if issues and result.language == "en" and language in {"", "en"} and not quality.uncertain:
        try:
            retry = recognize(audio, quality.selected.channel, model="small.en", language="en")
            retry_issues = uncertainty(retry, "en")
            if len(retry_issues) < len(issues):
                result, issues, selected = retry, retry_issues, "small.en"
        except CampusError:
            issues += ("selective_recheck_unavailable",)
    if quality.uncertain:
        issues += ("audio_quality_or_speech_uncertain",)
    elif not result.segments:
        issues += ("speech_not_recognized",)
    chunk = Chunk(
        fingerprint=fingerprint,
        interval=span,
        quality=quality,
        language=result.language,
        model=selected,
        passages=passages(result, span, expected_language=language),
        issues=issues,
    )
    private_write(path, chunk.model_dump_json().encode())
    return chunk, False
