from pathlib import Path

import pytest

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing import preparation_audio
from tum_mcp.lecture_processing.chunk_store import Chunk, StagedError
from tum_mcp.lecture_processing.preparation_audio import RecognizerUnavailable, prepare_audio
from tum_mcp.lecture_processing.transcript_models import AudioQuality, Passage
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate


def test_shared_model_failure_does_not_download_the_rest_of_a_long_lecture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloaded = []

    def acquire(span: Interval):
        downloaded.append(span.end_s - span.start_s)
        return ()

    def unavailable(*args, **kwargs):
        raise RecognizerUnavailable(Code.CAPABILITY_UNSUPPORTED, "Synthetic missing shared model")

    monkeypatch.setattr(preparation_audio, "run_span", unavailable)
    result = prepare_audio(evaluate(RecordingTiming(duration_s=7200)), tmp_path, "fixture", acquire)
    assert not result.processed and sum(downloaded) <= 30
    assert result.issues


def test_identical_preflight_failures_stop_before_the_full_scan_and_name_their_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloaded = []

    def acquire(span: Interval):
        downloaded.append(span.end_s - span.start_s)
        return ()

    def short(*args, **kwargs):
        raise StagedError(
            "decode",
            CampusError(
                Code.INVALID_RESPONSE,
                "Decoded audio does not cover its declared original-time interval.",
            ),
        )

    monkeypatch.setattr(preparation_audio, "run_span", short)
    result = prepare_audio(evaluate(RecordingTiming(duration_s=7200)), tmp_path, "fixture", acquire)
    # Then only the samples were fetched, and each failure says where and why.
    assert sum(downloaded) <= 120 and not result.processed
    assert "stopped_after_preflight" in result.issues
    assert {(item.scope, item.stage, item.code) for item in result.failures} == {
        ("preflight", "decode", "invalid_response")
    }
    assert result.failures[0].reason == "decoded_audio_does_not_cover_its_declared_original"


def test_a_chunk_specific_acquisition_failure_stays_partial_with_its_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def acquire(span: Interval):
        if span.start_s >= 600:
            raise CampusError(Code.INVALID_RESPONSE, "Media byte range did not match the request.")
        return ()

    def recognized(validity, span: Interval, *args, **kwargs):
        quality = AudioQuality.model_validate(
            {
                "duration_s": span.end_s - span.start_s,
                "channels": [
                    {
                        "channel": 0,
                        "rms": 0.1,
                        "clipped_fraction": 0,
                        "windows": [{"start_s": 0, "end_s": 1, "speech_s": 1}],
                    }
                ],
            }
        )
        return Chunk(
            fingerprint="b" * 64,
            interval=span,
            quality=quality,
            language="en",
            model="injected-protocol",
            passages=(),
        ), False

    monkeypatch.setattr(preparation_audio, "run_span", recognized)
    result = prepare_audio(evaluate(RecordingTiming(duration_s=1200)), tmp_path, "fixture", acquire)
    # Then earlier chunks stay processed and the failed ones name acquisition with their time.
    assert result.processed and result.processed[0].start_s == 0
    failed = [item for item in result.failures if item.scope.startswith("chunk_")]
    assert failed and {item.stage for item in failed} == {"acquire"}
    assert all(item.interval.end_s > 600 for item in failed)
    assert "stopped_after_preflight" not in result.issues


def test_three_quiet_samples_cannot_discard_speech_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sampled(validity, span: Interval, *args, **kwargs):
        duration = span.end_s - span.start_s
        speech = duration > 30
        quality = AudioQuality.model_validate(
            {
                "duration_s": duration,
                "channels": [
                    {
                        "channel": 0,
                        "rms": 0.1 if speech else 0,
                        "clipped_fraction": 0,
                        "windows": [
                            {"start_s": 0, "end_s": duration, "speech_s": 10 if speech else 0}
                        ],
                    }
                ],
            }
        )
        passages = (
            (
                Passage(
                    interval=Interval(start_s=span.start_s + 1, end_s=span.start_s + 2),
                    text="Synthetic speech outside the sampled windows.",
                    origin="asr",
                ),
            )
            if speech
            else ()
        )
        return Chunk(
            fingerprint="a" * 64,
            interval=span,
            quality=quality,
            language="en",
            model="injected-protocol",
            passages=passages,
            issues=() if speech else ("quiet_sample",),
        ), False

    monkeypatch.setattr(preparation_audio, "run_span", sampled)
    result = prepare_audio(
        evaluate(RecordingTiming(duration_s=1200)), tmp_path, "fixture", lambda span: ()
    )
    assert result.processed == (Interval(start_s=0, end_s=1200),)
    assert result.passages and "representative_sample_uncertain" in result.issues
