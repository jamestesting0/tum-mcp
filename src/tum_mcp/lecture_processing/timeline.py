"""Explicit decoded/chunk-to-original-time mapping and safe recording links."""

import math
from typing import Literal, assert_never

from pydantic import Field, FiniteFloat, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval, Recording
from tum_mcp.settings import Frozen


class MapPiece(Frozen):
    local_start_s: FiniteFloat
    original: Interval

    @property
    def local_end_s(self) -> float:
        return self.local_start_s + (self.original.end_s - self.original.start_s)


class Timeline(Frozen):
    pieces: tuple[MapPiece, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def ordered(self) -> "Timeline":
        for first, second in zip(self.pieces, self.pieces[1:], strict=False):
            if (
                first.local_end_s > second.local_start_s
                or first.original.end_s > second.original.start_s
            ):
                raise ValueError(
                    "Timeline pieces must be ordered, nonoverlapping, and at original speed."
                )
        return self

    def to_original(self, seconds: float, *, endpoint: Literal["start", "end"] = "start") -> float:
        if not math.isfinite(seconds):
            raise CampusError(Code.INVALID_RESPONSE, "A timestamp must be finite.")
        match endpoint:
            case "start":
                pieces = tuple(reversed(self.pieces))
            case "end":
                pieces = self.pieces
            case unreachable:
                assert_never(unreachable)
        for piece in pieces:
            if piece.local_start_s <= seconds <= piece.local_end_s:
                return piece.original.start_s + (seconds - piece.local_start_s)
        raise CampusError(Code.INVALID_RESPONSE, "Timestamp is outside verified timeline pieces.")


def watch_link(recording: Recording, seconds: float) -> str:
    if not math.isfinite(seconds) or not 0 <= seconds <= recording.duration_s:
        raise CampusError(Code.INVALID_RESPONSE, "Citation is outside the original recording.")
    base = (
        "https://example.invalid/lectures/synthetic"
        if recording.synthetic
        else f"https://live.rbg.tum.de/w/{recording.course_slug}/{recording.recording_id}"
    )
    return f"{base}?t={math.floor(seconds)}"
