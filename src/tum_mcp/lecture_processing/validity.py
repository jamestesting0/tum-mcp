"""The whole-silence terminal gate, before every content acquisition or cache read."""

from typing import Literal

from pydantic import Field

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval, Seconds, SilenceMarker, merge_intervals
from tum_mcp.settings import Frozen


class RecordingTiming(Frozen):
    duration_s: Seconds | None = None
    silences: tuple[SilenceMarker, ...] = Field(default=(), max_length=3000)
    start_offset_s: Seconds | None = None
    end_offset_s: Seconds | None = None


class Validity(Frozen):
    status: Literal["unknown", "eligible", "invalid"]
    reason: str
    duration_s: Seconds | None
    eligible: tuple[Interval, ...] = ()
    excluded: tuple[Interval, ...] = ()


def _complement(duration: float, exclusions: tuple[Interval, ...]) -> tuple[Interval, ...]:
    cursor = 0.0
    result: list[Interval] = []
    for span in exclusions:
        if cursor < span.start_s:
            result.append(Interval(start_s=cursor, end_s=span.start_s))
        cursor = span.end_s
    if cursor < duration:
        result.append(Interval(start_s=cursor, end_s=duration))
    return tuple(result)


def evaluate(timing: RecordingTiming) -> Validity:
    """Use true duration and exact gaps; provider rounding never erases positive gaps."""
    duration = timing.duration_s
    if duration is None or duration == 0:
        return Validity(status="unknown", reason="actual_duration_required", duration_s=duration)
    silent: list[Interval] = []
    for marker in timing.silences:
        if marker.end < marker.start:
            raise CampusError(Code.INVALID_RESPONSE, "Provider silence marker is reversed.")
        start, end = min(marker.start, duration), min(marker.end, duration)
        if start < end:
            silent.append(Interval(start_s=start, end_s=end))
    merged = merge_intervals(tuple(silent))
    whole = Interval(start_s=0, end_s=duration)
    if merged == (whole,):
        return Validity(
            status="invalid",
            reason="whole_recording_silence",
            duration_s=duration,
            excluded=(whole,),
        )
    start = timing.start_offset_s or 0
    end = min(timing.end_offset_s or duration, duration)
    if not 0 <= start < end:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Recording cut has no verified playable range."
        )
    cuts = ()
    if start > 0:
        cuts += (Interval(start_s=0, end_s=start),)
    if end < duration:
        cuts += (Interval(start_s=end, end_s=duration),)
    excluded = merge_intervals(merged + cuts)
    eligible = _complement(duration, excluded)
    if not eligible:
        return Validity(
            status="invalid", reason="no_eligible_content", duration_s=duration, excluded=excluded
        )
    return Validity(
        status="eligible" if merged else "unknown",
        reason="partial_silence_excluded"
        if merged
        else "silence_metadata_absent_preflight_required",
        duration_s=duration,
        eligible=eligible,
        excluded=excluded,
    )


def require_content(validity: Validity) -> None:
    """Call before content cache/import/captions/media/visual/model operations."""
    if validity.status == "invalid":
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, f"Recording invalid: {validity.reason}.")
    if not validity.eligible:
        raise CampusError(
            Code.ACTION_REQUIRED, "Determine actual recording duration from metadata first."
        )
