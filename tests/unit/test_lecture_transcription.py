import json
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.lecture_evidence import Interval, SilenceMarker
from tum_mcp.lecture_processing.captions import webvtt
from tum_mcp.lecture_processing.chunk_store import process_chunk
from tum_mcp.lecture_processing.transcript_models import AudioQuality, Passage, Recognition
from tum_mcp.lecture_processing.transcription import (
    chunks,
    deduplicate,
    passages,
    recognize,
    uncertainty,
)
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate


def test_long_retained_regions_have_five_second_overlap_without_crossing_silence() -> None:
    validity = evaluate(
        RecordingTiming(duration_s=1400, silences=(SilenceMarker(start=1200, end=1300),))
    )
    assert chunks(validity) == tuple(
        Interval(start_s=a, end_s=b) for a, b in ((0, 600), (595, 1195), (1190, 1200), (1300, 1400))
    )


def test_all_silent_recording_cannot_enter_caption_or_chunk_processing() -> None:
    validity = evaluate(RecordingTiming(duration_s=12, silences=(SilenceMarker(start=0, end=12),)))
    for operation in (lambda: chunks(validity), lambda: webvtt(b"invalid imported text", validity)):
        with pytest.raises(CampusError, match="invalid"):
            operation()


def test_imported_captions_keep_original_time_and_mark_crossing_cues() -> None:
    validity = evaluate(RecordingTiming(duration_s=20, silences=(SilenceMarker(start=5, end=10),)))
    result = webvtt(b"WEBVTT\n\n00:04.000 --> 00:12.000\nA &lt; B\n", validity)
    assert [
        (p.interval.start_s, p.interval.end_s, p.text, bool(p.uncertainty)) for p in result
    ] == [(4, 5, "A < B", True), (10, 12, "A < B", True)]


@pytest.mark.parametrize(
    "payload",
    [
        b"WEBVTT\n\n00:99.000 --> 01:00.000\nx",
        b"WEBVTT\n\n00:04.000 --> 00:25.000\nx",
        b"WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00.000,MPEGTS:90000\n\n",
    ],
)
def test_unverified_or_out_of_bounds_caption_clocks_are_rejected(payload: bytes) -> None:
    with pytest.raises(CampusError):
        webvtt(payload, evaluate(RecordingTiming(duration_s=20)))


def test_selected_channel_preserves_speech_when_other_channel_is_broken() -> None:
    quality = AudioQuality.model_validate(
        {
            "duration_s": 30,
            "channels": [
                {
                    "channel": 0,
                    "rms": 1,
                    "clipped_fraction": 1,
                    "windows": [{"start_s": 0, "end_s": 30, "speech_s": 30}],
                },
                {
                    "channel": 1,
                    "rms": 0.1,
                    "clipped_fraction": 0,
                    "windows": [{"start_s": 0, "end_s": 30, "speech_s": 20}],
                },
            ],
        }
    )
    assert quality.selected.channel == 1 and not quality.uncertain


def recognition(text: str = "A classical bit.", **changes: object) -> Recognition:
    return Recognition.model_validate(
        {
            "language": "en",
            "segments": [
                {
                    "start": 1,
                    "end": 2,
                    "text": text,
                    "avg_logprob": -0.2,
                    "no_speech_prob": 0.1,
                    "compression_ratio": 1,
                    "words": [{"start": 1, "end": 2, "word": text, "probability": 0.9}],
                    **changes,
                }
            ],
        }
    )


def test_timed_words_are_projected_into_original_recording_clock() -> None:
    result = passages(recognition(), Interval(start_s=1200, end_s=1210))
    assert result[0].interval == Interval(start_s=1201, end_s=1202)
    assert result[0].words[0].start == 1201


@pytest.mark.parametrize(
    "result", [recognition("thank you " * 15), recognition(avg_logprob=-2, no_speech_prob=0.9)]
)
def test_repetition_and_nonspeech_hallucinations_do_not_become_teaching(
    result: Recognition,
) -> None:
    assert uncertainty(result)
    assert passages(result, Interval(start_s=0, end_s=10)) == ()


def test_language_flip_remains_explicitly_uncertain() -> None:
    result = recognition().model_copy(update={"language": "de"})
    assert (
        "language_changed"
        in passages(result, Interval(start_s=0, end_s=10), expected_language="en")[0].uncertainty
    )


def test_native_word_alignment_can_lead_the_sentence_boundary() -> None:
    result = recognition(start=1.02)
    output = passages(result, Interval(start_s=100, end_s=110))
    assert output[0].interval.start_s == output[0].words[0].start == 101


def test_empty_native_placeholder_does_not_discard_valid_chunk_teaching() -> None:
    result = recognition()
    placeholder = result.segments[0].model_copy(
        update={"start": 2, "end": 2, "text": "", "words": ()}
    )
    combined = result.model_copy(update={"segments": (*result.segments, placeholder)})
    assert passages(combined, Interval(start_s=0, end_s=10)) == passages(
        result, Interval(start_s=0, end_s=10)
    )


def test_overlap_duplicate_is_removed_but_later_repeated_explanation_is_kept() -> None:
    def passage(start: int) -> Passage:
        return Passage(
            interval=Interval(start_s=start, end_s=start + 4),
            text="A bit is zero or one.",
            origin="asr",
        )

    assert len(deduplicate((passage(598), passage(599), passage(620)))) == 2


def test_protocol_rejects_malformed_engine_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.lecture_processing import runtime

    monkeypatch.setattr(
        runtime,
        "model",
        lambda _: runtime.ModelAsset(
            path=tmp_path, revision="a" * 40, config_sha256="a" * 64, weights_sha256="b" * 64
        ),
    )
    monkeypatch.setattr(
        runtime,
        "call_worker",
        lambda *args, **kwargs: json.dumps(
            {"language": "en", "segments": [{"start": float("nan")}]}
        ).encode(),
    )
    with pytest.raises(CampusError, match="malformed"):
        recognize(tmp_path / "audio.wav", 0)


def test_english_recheck_cannot_translate_another_language(tmp_path: Path) -> None:
    with pytest.raises(CampusError, match="confirmed English"):
        recognize(tmp_path / "audio.wav", 0, model="small.en", language="de")


def test_unchanged_audio_resumes_without_recognition_and_source_change_regenerates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.lecture_processing import chunk_store

    calls = []
    quality = AudioQuality.model_validate(
        {
            "duration_s": 10,
            "channels": [
                {
                    "channel": 0,
                    "rms": 0.1,
                    "clipped_fraction": 0,
                    "windows": [{"start_s": 0, "end_s": 10, "speech_s": 5}],
                }
            ],
        }
    )
    monkeypatch.setattr(chunk_store, "analyze", lambda _: quality)

    def adapter(*args, **kwargs):
        calls.append(1)
        return recognition()

    monkeypatch.setattr(chunk_store, "recognize", adapter)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic protocol fixture")
    validity = evaluate(RecordingTiming(duration_s=10))
    span = Interval(start_s=0, end_s=10)
    first, reused = process_chunk(audio, span, validity, tmp_path / "chunks", "source-a")
    second, reused = process_chunk(audio, span, validity, tmp_path / "chunks", "source-a")
    assert first == second and reused and len(calls) == 1
    process_chunk(audio, span, validity, tmp_path / "chunks", "source-b")
    assert len(calls) == 2


def test_invalid_recording_rejects_even_an_existing_audio_cache(tmp_path: Path) -> None:
    validity = evaluate(RecordingTiming(duration_s=10, silences=(SilenceMarker(start=0, end=10),)))
    with pytest.raises(CampusError, match="invalid"):
        process_chunk(
            tmp_path / "nonexistent.wav", Interval(start_s=0, end_s=10), validity, tmp_path, "same"
        )


def test_caption_markup_does_not_erase_mathematical_inequalities() -> None:
    result = webvtt(
        b"WEBVTT\n\n00:00.000 --> 00:05.000\n<v Professor><b>A < B > C</b>\n",
        evaluate(RecordingTiming(duration_s=5)),
    )
    assert result[0].text == "A < B > C"
