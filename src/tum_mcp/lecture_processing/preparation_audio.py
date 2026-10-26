"""Representative preflight plus full retained-audio chunk processing and resume."""

import hashlib
import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval, merge_intervals
from tum_mcp.lecture_processing.audio import render_audio
from tum_mcp.lecture_processing.chunk_store import Chunk, process_chunk
from tum_mcp.lecture_processing.media import AcquiredSegment
from tum_mcp.lecture_processing.runtime import profile
from tum_mcp.lecture_processing.transcript_models import Passage
from tum_mcp.lecture_processing.transcription import (
    chunks,
    deduplicate,
    owned_passages,
    sample_spans,
)
from tum_mcp.lecture_processing.validity import Validity, require_content
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen
from tum_mcp.study_store import confined


class AudioResult(Frozen):
    passages: tuple[Passage, ...] = ()
    processed: tuple[Interval, ...] = ()
    uncertain: tuple[Interval, ...] = ()
    issues: tuple[str, ...] = ()
    reused: int = 0
    inference_s: float = 0


def run_span(
    validity: Validity,
    span: Interval,
    segments: tuple[AcquiredSegment, ...],
    directory: Path,
    revision: str,
    language: str,
) -> tuple[Chunk, bool]:
    require_content(validity)
    identity = [
        revision,
        profile(),
        language,
        span.model_dump(),
        [
            (item.sha256, item.initialization_sha256, item.segment.span.model_dump())
            for item in segments
        ],
        "audio-v2-periods",
    ]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    path = confined(directory, f"prepared-{key}.json")
    if path.is_file():
        if path.stat().st_size > 8 * 1024**2:
            raise CampusError(Code.INVALID_RESPONSE, "Audio checkpoint exceeds its bound.")
        try:
            previous = Chunk.model_validate_json(path.read_bytes())
            if previous.interval == span:
                return previous, True
        except ValidationError:
            raise CampusError(Code.INVALID_RESPONSE, "Audio checkpoint is malformed.") from None
    with tempfile.TemporaryDirectory(prefix="audio-", dir=directory) as folder:
        audio = render_audio(segments, span, Path(folder))
        chunk, cached = process_chunk(
            audio, span, validity, directory / "chunks", revision, language=language
        )
    private_write(path, chunk.model_dump_json().encode())
    return chunk, cached


def prepare_audio(
    validity: Validity,
    directory: Path,
    revision: str,
    acquire: Callable[[Interval], tuple[AcquiredSegment, ...]],
    *,
    language: str = "",
    progress: Callable[[AudioResult], None] | None = None,
) -> AudioResult:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    issues: list[str] = []
    result: list[Passage] = []
    processed: list[Interval] = []
    uncertain: list[Interval] = []
    reused = 0
    inference_s = 0.0
    detected: list[str] = []
    # Samples never invalidate a lecture. Their media is reused during the full scan.
    for span in sample_spans(validity):
        try:
            started = time.monotonic()
            sample, cached = run_span(validity, span, acquire(span), directory, revision, language)
            inference_s += time.monotonic() - started if not cached else 0
            reused += cached
            if not sample.quality.uncertain and sample.passages and not sample.issues:
                detected.append(sample.language)
            if sample.issues:
                issues.append("representative_sample_uncertain")
        except CampusError as error:
            issues.append(f"preflight_{error.code.value.lower()}")
    expected = language or (max(set(detected), key=detected.count) if detected else "")
    windows = chunks(validity)
    for index, span in enumerate(windows):
        try:
            started = time.monotonic()
            chunk, cached = run_span(validity, span, acquire(span), directory, revision, expected)
            inference_s += time.monotonic() - started if not cached else 0
            reused += cached
            owned = Interval(
                start_s=span.start_s
                + (2.5 if index and windows[index - 1].end_s > span.start_s else 0),
                end_s=span.end_s
                - (
                    2.5
                    if index + 1 < len(windows) and windows[index + 1].start_s < span.end_s
                    else 0
                ),
            )
            result.extend(owned_passages(chunk.passages, owned))
            processed.append(span)
            if chunk.issues:
                uncertain.append(span)
                issues.extend(chunk.issues)
        except CampusError as error:
            issues.append(f"chunk_{index}_{error.code.value.lower()}")
        if progress is not None:
            progress(
                AudioResult(
                    processed=merge_intervals(tuple(processed)),
                    uncertain=merge_intervals(tuple(uncertain)),
                    reused=reused,
                )
            )
    return AudioResult(
        passages=deduplicate(tuple(result)),
        processed=merge_intervals(tuple(processed)),
        uncertain=merge_intervals(tuple(uncertain)),
        issues=tuple(sorted(set(issues))),
        reused=reused,
        inference_s=inference_s,
    )
