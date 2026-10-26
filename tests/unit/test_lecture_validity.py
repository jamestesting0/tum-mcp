import math

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.lecture_evidence import Interval, Recording, SilenceMarker
from tum_mcp.lecture_processing.timeline import MapPiece, Timeline, watch_link
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate, require_content


def test_full_marked_silence_stops_before_any_cached_content_read(tmp_path) -> None:
    cached = tmp_path / "old-transcript.txt"
    cached.write_text("Old apparently usable transcript must not be reused.")
    validity = evaluate(
        RecordingTiming(
            duration_s=7821.945,
            silences=(SilenceMarker(start=0, end=7822),),
        )
    )
    with pytest.raises(CampusError, match="whole_recording_silence"):
        require_content(validity)
        cached.read_text()
        pytest.fail("Content cache was read after whole-silence rejection")
    assert validity.status == "invalid"
    assert validity.eligible == ()


def test_contiguous_markers_cover_whole_recording_but_real_gap_does_not() -> None:
    full = evaluate(
        RecordingTiming(
            duration_s=100,
            silences=(
                SilenceMarker(start=50, end=100),
                SilenceMarker(start=0, end=50),
            ),
        )
    )
    gap = evaluate(
        RecordingTiming(
            duration_s=100,
            silences=(
                SilenceMarker(start=50.001, end=100),
                SilenceMarker(start=0, end=50),
            ),
        )
    )
    assert full.status == "invalid"
    assert gap.eligible == (Interval(start_s=50, end_s=50.001),)


def test_partial_tail_uses_actual_duration_and_keeps_absolute_time() -> None:
    result = evaluate(
        RecordingTiming(
            duration_s=5488.066559,
            silences=(SilenceMarker(start=4877, end=5488.1),),
        )
    )
    assert result.eligible == (Interval(start_s=0, end_s=4877),)
    assert result.excluded == (Interval(start_s=4877, end_s=5488.066559),)
    assert result.status == "eligible"


def test_absent_markers_require_preflight_and_unknown_duration_blocks_content() -> None:
    absent = evaluate(RecordingTiming(duration_s=600))
    assert absent.status == "unknown" and absent.eligible == (Interval(start_s=0, end_s=600),)
    require_content(absent)
    missing_duration = evaluate(RecordingTiming())
    with pytest.raises(CampusError, match="duration"):
        require_content(missing_duration)


def test_cuts_clip_original_timeline_without_changing_watch_seconds() -> None:
    result = evaluate(
        RecordingTiming(
            duration_s=600,
            start_offset_s=100,
            end_offset_s=500,
            silences=(SilenceMarker(start=200, end=250),),
        )
    )
    assert result.eligible == (Interval(start_s=100, end_s=200), Interval(start_s=250, end_s=500))
    assert result.excluded == (
        Interval(start_s=0, end_s=100),
        Interval(start_s=200, end_s=250),
        Interval(start_s=500, end_s=600),
    )


def test_concatenated_chunk_boundary_maps_word_start_and_end_independently() -> None:
    timeline = Timeline(
        pieces=(
            MapPiece(local_start_s=0, original=Interval(start_s=100, end_s=110)),
            MapPiece(local_start_s=10, original=Interval(start_s=200, end_s=220)),
        )
    )
    assert timeline.to_original(10) == 200
    assert timeline.to_original(10, endpoint="end") == 110
    assert timeline.to_original(11.5) == 201.5
    with pytest.raises(CampusError):
        timeline.to_original(31)


def test_decoded_pts_and_fractional_frame_time_keep_capture_moment() -> None:
    timeline = Timeline(
        pieces=(
            MapPiece(local_start_s=1.4, original=Interval(start_s=2399.666622, end_s=2419.666622)),
        )
    )
    captured = timeline.to_original(1.4 + 15 * 1001 / 30000)
    assert math.isclose(captured, 2400.167122)
    recording = Recording(
        course_slug="950943622",
        course_id=2464,
        recording_id=76477,
        recorded_on="2026-10-14",
        duration_s=5488.066559,
    )
    assert watch_link(recording, captured) == "https://live.rbg.tum.de/w/950943622/76477?t=2400"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 601])
def test_link_rejects_nonfinite_or_outside_original_time(value: float) -> None:
    recording = Recording(
        course_slug="x", course_id=1, recording_id=2, recorded_on="2026-10-14", duration_s=600
    )
    with pytest.raises(CampusError):
        watch_link(recording, value)
