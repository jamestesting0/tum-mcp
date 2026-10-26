from pathlib import Path

import pytest

from tum_mcp.errors import Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing import preparation_audio
from tum_mcp.lecture_processing.chunk_store import Chunk
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
