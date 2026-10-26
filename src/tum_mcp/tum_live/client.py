"""Verified identity/course/recording membership over existing bounded service HTTP."""

import hashlib
import re
import time
from collections.abc import Sequence

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate
from tum_mcp.parsing import decode
from tum_mcp.settings import Frozen, Provider
from tum_mcp.transport import API
from tum_mcp.tum_live.models import (
    CoursePage,
    CourseSummary,
    InvalidRecordingMetadata,
    RecordingMetadata,
    RecordingPage,
    StreamSummary,
)
from tum_mcp.tum_live.wire import Course, CourseResponse, CoursesResponse, Identity, Stream, Watch


def _page[T: Frozen](
    items: Sequence[T], cursor: str | None, limit: int
) -> tuple[tuple[T, ...], str | None]:
    if not 1 <= limit <= 100:
        raise CampusError(Code.SCOPE_DENIED, "Page limit must be between 1 and 100.")
    digest = hashlib.sha256(
        b"\n".join(item.model_dump_json().encode() for item in items)
    ).hexdigest()
    offset = 0
    if cursor is not None:
        match = re.fullmatch(r"v1:([a-f0-9]{64}):(\d{1,5})", cursor)
        if match is None or match[1] != digest:
            raise CampusError(
                Code.STALE_RESULT, "Directory changed or cursor is invalid; restart pagination."
            )
        offset = int(match[2])
        if offset > len(items):
            raise CampusError(Code.SCOPE_DENIED, "Cursor exceeds this directory.")
    selected = tuple(items[offset : offset + limit])
    following = offset + len(selected)
    return selected, f"v1:{digest}:{following}" if following < len(items) else None


def _course(value: Course) -> CourseSummary:
    return CourseSummary(id=value.id, slug=value.slug, name=value.name)


def _stream(value: Stream) -> StreamSummary:
    return StreamSummary(
        id=value.id,
        title=value.display_name or value.name or f"Lecture: {value.start.date()}",
        start=value.start,
        recording=value.recording,
    )


class TumLive:
    def __init__(self, api: API) -> None:
        if api.account.provider != Provider.TUM_LIVE:
            raise CampusError(Code.SCOPE_DENIED, "A TUM-Live account is required.")
        self.api = api

    def identity(self) -> int:
        value = decode(Identity, self.api.get("/api/v2/users/me"))
        if value.user is None:
            raise CampusError(Code.AUTH_REQUIRED, "Connect the TUM-Live service first.")
        if str(value.user.id) != self.api.account.principal:
            raise CampusError(Code.SCOPE_DENIED, "Connected TUM-Live identity changed.")
        return value.user.id

    def courses(self, cursor: str | None = None, limit: int = 20) -> CoursePage:
        """List enrolled courses; a known accessible slug can be resolved separately."""
        self.identity()
        wire = decode(CoursesResponse, self.api.get("/api/v2/courses/enrolled"))
        ordered = tuple(_course(item) for item in sorted(wire.courses, key=lambda item: item.id))
        selected, following = _page(ordered, cursor, limit)
        return CoursePage(account_id=self.api.account.id, courses=selected, next_cursor=following)

    def course(self, slug: str) -> Course:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", slug) is None:
            raise CampusError(Code.SCOPE_DENIED, "Use an exact TUM-Live course slug.")
        wire = decode(CourseResponse, self.api.get(f"/api/v2/courses/{slug}"))
        if wire.course.slug != slug or any(
            stream.course_id is not None and stream.course_id != wire.course.id
            for stream in wire.course.streams
        ):
            raise CampusError(Code.SCOPE_DENIED, "Course/recording membership did not match.")
        return wire.course

    def recordings(self, slug: str, cursor: str | None = None, limit: int = 20) -> RecordingPage:
        self.identity()
        course = self.course(slug)
        ordered = tuple(
            _stream(item) for item in sorted(course.streams, key=lambda x: x.start, reverse=True)
        )
        selected, following = _page(ordered, cursor, limit)
        return RecordingPage(
            account_id=self.api.account.id,
            course=_course(course),
            recordings=selected,
            next_cursor=following,
        )

    def watch(self, slug: str, recording_id: int) -> Watch:
        """Private processing input. Media capabilities are excluded from repr/serialization."""
        if recording_id <= 0:
            raise CampusError(Code.SCOPE_DENIED, "Use a positive recording ID.")
        self.identity()
        course = self.course(slug)
        if recording_id not in {stream.id for stream in course.streams}:
            raise CampusError(
                Code.SCOPE_DENIED, "Requested recording is not in the selected course."
            )
        wire = decode(Watch, self.api.get(f"/api/v2/streams/{slug}/{recording_id}/watch"))
        if (
            wire.course.id != course.id
            or wire.course.slug != slug
            or wire.stream.id != recording_id
            or wire.stream.course_id not in {None, course.id}
        ):
            raise CampusError(
                Code.SCOPE_DENIED, "Watch metadata changed course/recording identity."
            )
        return wire

    def recording(
        self, slug: str, recording_id: int
    ) -> RecordingMetadata | InvalidRecordingMetadata:
        watch = self.watch(slug, recording_id)
        validity = evaluate(
            RecordingTiming(
                duration_s=watch.stream.duration,
                silences=watch.silences,
                start_offset_s=watch.start_offset,
                end_offset_s=watch.end_offset,
            )
        )
        if validity.status == "invalid":
            return InvalidRecordingMetadata(
                account_id=self.api.account.id,
                course_id=watch.course.id,
                course_slug=slug,
                recording_id=recording_id,
                source_link=f"{self.api.account.origin}/w/{slug}/{recording_id}",
                duration_s=validity.duration_s,
                reason=validity.reason,
                fetched_at=time.time(),
            )
        return RecordingMetadata(
            account_id=self.api.account.id,
            course=_course(watch.course),
            stream=_stream(watch.stream),
            source_link=f"{self.api.account.origin}/w/{slug}/{recording_id}",
            duration_s=watch.stream.duration,
            silences=watch.silences,
            start_offset_s=watch.start_offset,
            end_offset_s=watch.end_offset,
            subtitle_languages=watch.subtitle_languages,
            available_views=tuple(view.kind for view in watch.views),
            fetched_at=time.time(),
            validity=validity.status,
            reason=validity.reason,
        )
