"""Student lecture projections. Completion, staff data and original slide links are omitted."""

from pydantic import AwareDatetime, Field, RootModel

from tum_mcp.artemis_models import Exercise, Reference, Wire
from tum_mcp.settings import Frozen, PositiveId
from tum_moodle.models import TextPage


class Attachment(Wire):
    id: PositiveId
    name: str = "Attachment"
    link: str = Field(default="", exclude=True, repr=False)
    student_version: str | None = Field(default=None, alias="studentVersion", exclude=True)
    release_date: AwareDatetime | None = Field(default=None, alias="releaseDate")
    upload_date: AwareDatetime | None = Field(default=None, alias="uploadDate")
    version: int | None = None


class LectureUnit(Wire):
    id: PositiveId
    type: str
    name: str = ""
    release_date: AwareDatetime | None = Field(default=None, alias="releaseDate")
    visible: bool = Field(default=True, alias="visibleToStudents")
    content: str | None = Field(default=None, max_length=300000)
    description: str | None = Field(default=None, max_length=100000)
    source: str | None = None
    video_source: str | None = Field(default=None, alias="videoSource")
    attachment: Attachment | None = None
    exercise: Exercise | None = None


class LectureSummary(Wire):
    id: PositiveId
    title: str
    start_date: AwareDatetime | None = Field(default=None, alias="startDate")
    end_date: AwareDatetime | None = Field(default=None, alias="endDate")
    tutorial: bool = Field(default=False, alias="isTutorialLecture")


class LectureList(RootModel[tuple[LectureSummary, ...]]):
    pass


class Lecture(LectureSummary):
    course: Reference
    description: str | None = Field(default=None, max_length=100000)
    units: tuple[LectureUnit, ...] = Field(default=(), alias="lectureUnits")
    attachments: tuple[Attachment, ...] = ()


class LectureDirectory(Frozen):
    account_id: str
    course_id: int
    lectures: tuple[LectureSummary, ...]
    fetched_at: float
    source_link: str
    untrusted_content: bool = True


class LectureView(Frozen):
    account_id: str
    course_id: int
    lecture: Lecture
    unsupported_units: tuple[str, ...] = ()
    fetched_at: float
    source_link: str
    untrusted_content: bool = True


class AttachmentView(Frozen):
    account_id: str
    course_id: int
    lecture_id: int
    attachment_id: int
    title: str
    sha256: str
    total_pages: int
    pages: tuple[TextPage, ...]
    truncated: bool
    saved_path: str | None = None
    warnings: tuple[str, ...]
    fetched_at: float
    source_link: str
    untrusted_content: bool = True
