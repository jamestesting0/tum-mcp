"""Credential-free, bounded metadata returned to tools and course authors."""

from typing import Literal

from pydantic import AwareDatetime

from tum_mcp.lecture_evidence import Seconds
from tum_mcp.settings import Frozen
from tum_mcp.tum_live.wire import Silence, Slug


class CourseSummary(Frozen):
    id: int
    slug: Slug
    name: str


class CoursePage(Frozen):
    account_id: str
    courses: tuple[CourseSummary, ...]
    next_cursor: str | None = None
    coverage: Literal["enrolled_only"] = "enrolled_only"


class StreamSummary(Frozen):
    id: int
    title: str
    start: AwareDatetime
    recording: bool


class RecordingPage(Frozen):
    account_id: str
    course: CourseSummary
    recordings: tuple[StreamSummary, ...]
    next_cursor: str | None = None


class RecordingMetadata(Frozen):
    account_id: str
    course: CourseSummary
    stream: StreamSummary
    source_link: str
    duration_s: Seconds | None
    silences: tuple[Silence, ...]
    start_offset_s: Seconds | None
    end_offset_s: Seconds | None
    subtitle_languages: tuple[str, ...]
    available_views: tuple[str, ...]
    validity: Literal["unknown", "eligible"] = "unknown"
    reason: str = "validity_not_evaluated"
    fetched_at: float
    untrusted_content: bool = True


class InvalidRecordingMetadata(Frozen):
    account_id: str
    course_id: int
    course_slug: Slug
    recording_id: int
    source_link: str
    duration_s: Seconds | None
    validity: Literal["invalid"] = "invalid"
    reason: str
    fetched_at: float
