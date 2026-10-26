"""Narrow wire models; signed media capabilities never serialize or appear in repr."""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr

from tum_mcp.lecture_evidence import Seconds, SilenceMarker
from tum_mcp.settings import PositiveId

Slug = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")]


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class User(Wire):
    id: PositiveId


class Identity(Wire):
    user: User | None = None


class Stream(Wire):
    id: PositiveId
    course_id: PositiveId | None = Field(default=None, alias="courseId")
    name: str = Field(default="", max_length=2000)
    display_name: str = Field(default="", alias="displayName", max_length=2000)
    start: AwareDatetime
    end: AwareDatetime | None = None
    recording: bool = False
    live_now: bool = Field(default=False, alias="liveNow")
    duration: Seconds | None = None


class Course(Wire):
    id: PositiveId
    name: str = Field(max_length=2000)
    slug: Slug
    streams: tuple[Stream, ...] = Field(default=(), max_length=10000, exclude=True, repr=False)


class CourseResponse(Wire):
    course: Course


class CoursesResponse(Wire):
    courses: tuple[Course, ...] = Field(default=(), max_length=10000)


Silence = SilenceMarker


class Sprite(Wire):
    file_id: PositiveId = Field(alias="fileId")
    interval_s: int = Field(alias="intervalSeconds", gt=0, le=3600)


class View(Wire):
    kind: str = Field(max_length=100)
    playlist_url: SecretStr = Field(alias="playlistUrl", exclude=True, repr=False)
    sprite: Sprite | None = None


class Attachment(Wire):
    file_id: PositiveId = Field(alias="fileId")
    filename: str = Field(default="", max_length=500)


class Watch(Wire):
    course: Course
    stream: Stream
    views: tuple[View, ...] = Field(default=(), max_length=3, exclude=True, repr=False)
    start_offset: Seconds | None = Field(default=None, alias="startOffset")
    end_offset: Seconds | None = Field(default=None, alias="endOffset")
    silences: tuple[Silence, ...] = Field(default=(), max_length=3000)
    subtitle_languages: tuple[str, ...] = Field(
        default=(), alias="subtitleLanguages", max_length=30
    )
    attachments: tuple[Attachment, ...] = Field(
        default=(), max_length=100, exclude=True, repr=False
    )
