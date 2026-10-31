"""Representative preflight plus full retained-audio chunk processing and resume."""

import hashlib
import json
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval, merge_intervals
from tum_mcp.lecture_processing.audio import render_audio
from tum_mcp.lecture_processing.chunk_store import Chunk, StagedError, process_chunk, staged
from tum_mcp.lecture_processing.media import AcquiredSegment
from tum_mcp.lecture_processing.runtime import recognition_profile
from tum_mcp.lecture_processing.transcript_models import AudioFailure, Passage
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
    failures: tuple[AudioFailure, ...] = ()
    reused: int = 0
    inference_s: float = 0


class RecognizerUnavailable(CampusError):
    """A shared runtime/model failure; retrying every audio chunk cannot repair it."""


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
        recognition_profile(),
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
        previous = staged("cache", _checkpoint, path)
        if previous.interval == span:
            return previous, True
    with tempfile.TemporaryDirectory(prefix="audio-", dir=directory) as folder:
        audio = staged("decode", render_audio, segments, span, Path(folder))
        try:
            chunk, cached = staged(
                "recognize",
                process_chunk,
                audio,
                span,
                validity,
                directory / "chunks",
                revision,
                language=language,
            )
        except CampusError as error:
            if error.code in {
                Code.ACTION_REQUIRED,
                Code.CAPABILITY_UNSUPPORTED,
                Code.OFFLINE,
                Code.RATE_LIMITED,
            }:
                raise RecognizerUnavailable(
                    error.code,
                    "Shared lecture recognizer is unavailable; cached evidence was preserved.",
                ) from None
            raise
    private_write(path, chunk.model_dump_json().encode())
    return chunk, cached


def _checkpoint(path: Path) -> Chunk:
    if path.stat().st_size > 8 * 1024**2:
        raise CampusError(Code.INVALID_RESPONSE, "Audio checkpoint exceeds its bound.")
    try:
        return Chunk.model_validate_json(path.read_bytes())
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Audio checkpoint is malformed.") from None


def failure(scope: str, span: Interval, error: CampusError) -> AudioFailure:
    """Name a failed span's stage and reason from the code-authored message alone."""
    words = re.findall(r"[a-z]+", error.message.split(".")[0].lower())[:8]
    return AudioFailure(
        scope=scope,
        interval=span,
        stage=error.stage if isinstance(error, StagedError) else "acquire",
        code=error.code.value.lower(),
        reason="_".join(words) or "unspecified",
    )


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
    failures: list[AudioFailure] = []
    result: list[Passage] = []
    processed: list[Interval] = []
    uncertain: list[Interval] = []
    reused = 0
    inference_s = 0.0
    detected: list[str] = []
    # Samples never invalidate a lecture. Their media is reused during the full scan.
    samples = sample_spans(validity)
    for span in samples:
        try:
            started = time.monotonic()
            segments = staged("acquire", acquire, span)
            sample, cached = run_span(validity, span, segments, directory, revision, language)
            inference_s += time.monotonic() - started if not cached else 0
            reused += cached
            if not sample.quality.uncertain and sample.passages and not sample.issues:
                detected.append(sample.language)
            if sample.issues:
                issues.append("representative_sample_uncertain")
        except RecognizerUnavailable as error:
            return AudioResult(issues=(f"recognizer_{error.code.value.lower()}",))
        except CampusError as error:
            failures.append(failure("preflight", span, error))
            issues.append(f"preflight_{failures[-1].stage}_{failures[-1].code}")
    # Every sample failing the same way is a shared cause (media, decoder or recognizer
    # output), so the full scan would fail identically after downloading the whole lecture.
    if (
        len(samples) > 1
        and len(failures) == len(samples)
        and len({(item.stage, item.code, item.reason) for item in failures}) == 1
    ):
        return AudioResult(
            issues=tuple(sorted({*issues, "stopped_after_preflight"})),
            failures=tuple(failures),
            reused=reused,
            inference_s=inference_s,
        )
    expected = language or (max(set(detected), key=detected.count) if detected else "")
    windows = chunks(validity)
    for index, span in enumerate(windows):
        try:
            started = time.monotonic()
            segments = staged("acquire", acquire, span)
            chunk, cached = run_span(validity, span, segments, directory, revision, expected)
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
        except RecognizerUnavailable as error:
            issues.append(f"recognizer_{error.code.value.lower()}")
            break
        except CampusError as error:
            failures.append(failure(f"chunk_{index}", span, error))
            issues.append(f"chunk_{index}_{failures[-1].stage}_{failures[-1].code}")
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
        failures=tuple(failures),
        reused=reused,
        inference_s=inference_s,
    )
