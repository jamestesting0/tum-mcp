"""Pinned recognition, original-time passages, and conservative uncertainty checks."""

import re
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing import runtime
from tum_mcp.lecture_processing.timeline import MapPiece, Timeline
from tum_mcp.lecture_processing.transcript_models import AudioQuality, Passage, Recognition
from tum_mcp.lecture_processing.validity import Validity, require_content


def chunks(validity: Validity) -> tuple[Interval, ...]:
    require_content(validity)
    result: list[Interval] = []
    for span in validity.eligible:
        start = span.start_s
        while start < span.end_s:
            end = min(start + 600, span.end_s)
            result.append(Interval(start_s=start, end_s=end))
            if end == span.end_s:
                break
            start = end - 5
    return tuple(result)


def sample_spans(validity: Validity) -> tuple[Interval, ...]:
    """Three representative retained windows; silence exclusions keep their original clock."""
    require_content(validity)
    total = sum(span.end_s - span.start_s for span in validity.eligible)
    result: list[Interval] = []
    for fraction in (0.05, 0.5, 0.95):
        position = total * fraction
        for span in validity.eligible:
            length = span.end_s - span.start_s
            if position <= length:
                start = max(span.start_s, min(span.start_s + position - 15, span.end_s - 30))
                selected = Interval(start_s=start, end_s=min(start + 30, span.end_s))
                if selected not in result:
                    result.append(selected)
                break
            position -= length
    return tuple(result)


def analyze(audio: Path) -> AudioQuality:
    try:
        return AudioQuality.model_validate_json(runtime.call_worker("analyze", audio=str(audio)))
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Audio-quality result failed validation."
        ) from None


def recognize(audio: Path, channel: int, *, model: str = "base", language: str = "") -> Recognition:
    if language and not re.fullmatch(r"[a-z]{2,3}", language):
        raise CampusError(
            Code.INVALID_RESPONSE, "Use a two or three letter recognition language code."
        )
    if model == "small.en" and language != "en":
        raise CampusError(
            Code.SCOPE_DENIED, "The English recheck model requires confirmed English audio."
        )
    asset = runtime.model(model)
    try:
        return Recognition.model_validate_json(
            runtime.call_worker(
                "transcribe",
                audio=str(audio),
                channel=channel,
                model=str(asset.path),
                config_sha256=asset.config_sha256,
                weights_sha256=asset.weights_sha256,
                language=language,
            )
        )
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Recognition returned malformed timed words."
        ) from None


def uncertainty(result: Recognition, expected_language: str = "") -> tuple[str, ...]:
    issues: set[str] = set()
    if expected_language and result.language != expected_language:
        issues.add("language_changed")
    for segment in result.segments:
        words = re.findall(r"\w+", segment.text.lower())
        repeated = len(words) >= 12 and (
            max(Counter(words).values(), default=0) / len(words) > 0.7
            or any(
                all(word == words[index % width] for index, word in enumerate(words))
                for width in range(1, min(7, len(words) // 4 + 1))
            )
        )
        if segment.compression_ratio > 2.4 or repeated:
            issues.add("repetitive_recognition")
        if segment.avg_logprob < -1:
            issues.add("low_recognition_confidence")
        if segment.no_speech_prob > 0.6 and segment.avg_logprob < -1:
            issues.add("possible_nonspeech_hallucination")
    return tuple(sorted(issues))


def passages(
    result: Recognition, interval: Interval, *, expected_language: str = ""
) -> tuple[Passage, ...]:
    timeline = Timeline(pieces=(MapPiece(local_start_s=0, original=interval),))
    output: list[Passage] = []
    language_issue = (
        "language_changed" if expected_language and result.language != expected_language else ""
    )
    duration = interval.end_s - interval.start_s
    for segment in result.segments:
        if not segment.text.strip() and not segment.words:
            continue
        if not 0 <= segment.start < segment.end <= duration:
            raise CampusError(
                Code.INVALID_RESPONSE, "Recognition timing is outside its verified audio interval."
            )
        issues = uncertainty(Recognition(language=result.language, segments=(segment,)))
        if {"repetitive_recognition", "possible_nonspeech_hallucination"}.intersection(issues):
            continue
        first = min((word.start for word in segment.words), default=segment.start)
        last = max((word.end for word in segment.words), default=segment.end)
        first, last = min(first, segment.start), max(last, segment.end)
        if not 0 <= first < last <= duration or any(
            word.start > word.end for word in segment.words
        ):
            raise CampusError(Code.INVALID_RESPONSE, "Word timing is outside verified audio.")
        words = tuple(
            word.model_copy(
                update={
                    "start": timeline.to_original(word.start),
                    "end": timeline.to_original(word.end, endpoint="end"),
                }
            )
            for word in segment.words
        )
        output.append(
            Passage(
                interval=Interval(
                    start_s=timeline.to_original(first),
                    end_s=timeline.to_original(last, endpoint="end"),
                ),
                text=segment.text.strip(),
                origin="asr",
                words=words,
                uncertainty=", ".join(filter(None, (*issues, language_issue))),
            )
        )
    return tuple(output)


def deduplicate(passages: tuple[Passage, ...]) -> tuple[Passage, ...]:
    output: list[Passage] = []
    for passage in sorted(
        passages, key=lambda value: (value.interval.start_s, value.interval.end_s)
    ):
        normalized = " ".join(re.findall(r"\w+", passage.text.casefold()))
        previous = next(
            (
                item
                for item in reversed(output)
                if item.interval.end_s > passage.interval.start_s
                and " ".join(re.findall(r"\w+", item.text.casefold())) == normalized
            ),
            None,
        )
        if previous is None:
            output.append(passage)
    return tuple(output)


def owned_passages(items: tuple[Passage, ...], owned: Interval) -> tuple[Passage, ...]:
    """Split overlap ownership at its midpoint using original-time word centers."""
    result: list[Passage] = []
    for item in items:
        words = tuple(
            word
            for word in item.words
            if owned.start_s <= (word.start + word.end) / 2 < owned.end_s
        )
        if words:
            result.append(
                item.model_copy(
                    update={
                        "interval": Interval(start_s=words[0].start, end_s=words[-1].end),
                        "words": words,
                        "text": "".join(word.word for word in words).strip(),
                    }
                )
            )
        elif (
            not item.words
            and owned.start_s <= (item.interval.start_s + item.interval.end_s) / 2 < owned.end_s
        ):
            result.append(
                item.model_copy(
                    update={
                        "uncertainty": ", ".join(
                            filter(None, (item.uncertainty, "word_timing_missing"))
                        )
                    }
                )
            )
    return tuple(result)
