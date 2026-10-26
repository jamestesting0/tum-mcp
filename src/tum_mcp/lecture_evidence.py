"""Finite recording-time evidence and honest coverage for lecture preparation."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_content import Text
from tum_mcp.study_models import Digest, Key

Seconds = Annotated[FiniteFloat, Field(ge=0, le=28800)]


class SilenceMarker(Frozen):
    start: Seconds
    end: Seconds


class Interval(Frozen):
    start_s: Seconds
    end_s: Seconds

    @model_validator(mode="after")
    def increasing(self) -> "Interval":
        if self.end_s <= self.start_s:
            raise ValueError("Recording intervals must have positive duration.")
        return self


def merge_intervals(intervals: tuple[Interval, ...]) -> tuple[Interval, ...]:
    result: list[Interval] = []
    for span in sorted(intervals, key=lambda item: item.start_s):
        if result and span.start_s <= result[-1].end_s:
            result[-1] = Interval(
                start_s=result[-1].start_s, end_s=max(result[-1].end_s, span.end_s)
            )
        else:
            result.append(span)
    return tuple(result)


def distinct_intervals(intervals: tuple[Interval, ...]) -> None:
    if any(a.end_s > b.start_s for a, b in zip(intervals, intervals[1:], strict=False)):
        raise ValueError("Coverage intervals must be ordered and disjoint.")


class Recording(Frozen):
    course_slug: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")]
    course_id: int = Field(gt=0)
    recording_id: int = Field(gt=0)
    recorded_on: date
    duration_s: Seconds = Field(gt=0)
    synthetic: bool = False

    @property
    def key(self) -> str:
        return f"live-{self.course_id}-{self.recording_id}"


class LectureCoverage(Frozen):
    status: Literal["complete", "partial"]
    eligible: tuple[Interval, ...] = Field(min_length=1, max_length=3000)
    processed: tuple[Interval, ...] = Field(default=(), max_length=3000)
    excluded: tuple[Interval, ...] = Field(default=(), max_length=3000)
    missing: tuple[Interval, ...] = Field(default=(), max_length=3000)
    uncertain: tuple[Interval, ...] = Field(default=(), max_length=3000)
    reviewed: bool = False

    @model_validator(mode="after")
    def partition(self) -> "LectureCoverage":
        for collection in (
            self.eligible,
            self.processed,
            self.excluded,
            self.missing,
            self.uncertain,
        ):
            distinct_intervals(collection)
        distinct_intervals(tuple(sorted(self.processed + self.missing, key=lambda x: x.start_s)))
        if merge_intervals(self.processed + self.missing) != merge_intervals(self.eligible):
            raise ValueError("Processed and missing intervals must partition eligible time.")
        distinct_intervals(tuple(sorted(self.eligible + self.excluded, key=lambda x: x.start_s)))
        for span in self.uncertain:
            if not any(
                item.start_s <= span.start_s < span.end_s <= item.end_s
                for item in merge_intervals(self.processed)
            ):
                raise ValueError("Uncertainty must annotate processed evidence.")
        if self.status == "complete" and (self.missing or self.uncertain or not self.reviewed):
            raise ValueError("Complete notes require full coverage and completed semantic review.")
        return self


class Evidence(Frozen):
    key: Key
    source_key: Key
    source_sha256: Digest
    kind: Literal["subtitle", "asr", "frame", "document"]
    recording_id: int | None = Field(default=None, gt=0)
    interval: Interval | None = None
    locator: str = Field(default="", max_length=500)
    reviewed: bool = False
    uncertainty: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def location(self) -> "Evidence":
        if self.kind == "document":
            if (
                not self.locator.strip()
                or self.interval is not None
                or self.recording_id is not None
            ):
                raise ValueError("Supporting documents need a locator, not recording time.")
        elif self.interval is None or self.recording_id is None:
            raise ValueError(
                "Recording evidence needs its recording identity and original interval."
            )
        return self


class Crop(Frozen):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    original_width: int = Field(gt=0, le=16000)
    original_height: int = Field(gt=0, le=16000)
    original_sha256: Digest

    @model_validator(mode="after")
    def fits(self) -> "Crop":
        if (
            self.x + self.width > self.original_width
            or self.y + self.height > self.original_height
            or self.original_width * self.original_height > 16_000_000
        ):
            raise ValueError("Crop must fit its verified original image.")
        return self


class Figure(Frozen):
    evidence: Key
    sha256: Digest
    asset: Annotated[str, Field(pattern=r"^lecture-assets/[a-f0-9]{64}\.(jpg|png|webp)$")]
    width: int = Field(gt=0, le=2048)
    height: int = Field(gt=0, le=16000)
    captured_at_s: Seconds
    caption: Text
    alt: Text
    crop: Crop | None = None

    @model_validator(mode="after")
    def safe_asset(self) -> "Figure":
        if (
            self.asset.split("/")[-1].split(".")[0] != self.sha256
            or self.width * self.height > 16_000_000
        ):
            raise ValueError("Figure path/hash or pixel budget does not match.")
        return self
