"""Projections of the student's own achievements and study progress."""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.tumonline.auth import STUDIES, Get
from tum_mcp.tumonline.courses import Text
from tum_mcp.tumonline.studies import StudyResponse

ACHIEVEMENTS: Final = "/tumonline/ee/rest/slc.xm.ac/achievements"
MY_STUDIES: Final = "/tumonline/ee/rest/slc.cm.cs/student/myStudies"


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class CourseNumber(Wire):
    courseNumber: str = Field(max_length=200)


class AchievedCourse(Wire):
    courseTitle: Text
    courseNumber: CourseNumber | None = None


class Semester(Wire):
    shortName: Text


class Instant(Wire):
    value: str = Field(max_length=40)


class Grade(Wire):
    nameShort: str = Field(max_length=40)
    name: Text | None = None
    isPositive: bool | None = None


class StudyName(Wire):
    studyName: Text


class AchievementWire(Wire):
    achievementType: str = Field(max_length=60)
    achievementStatusType: str = Field(max_length=60)
    cpCourseLibDto: AchievedCourse
    semesterLibDto: Semester | None = None
    achievementDate: Instant | None = None
    gradeDto: Grade
    credits: float | None = None
    studyBasicInfoLibDto: StudyName | None = None


class AchievementContent(Wire):
    achievementDto: AchievementWire


class AchievementResource(Wire):
    content: AchievementContent


class AchievementResponse(Wire):
    resource: tuple[AchievementResource, ...] = Field(max_length=2000)


class Bar(Wire):
    progress: float
    tooltip: Text


class ProgressBar(Wire):
    barElements: tuple[Bar, ...] = Field(max_length=20)


class Achievement(Frozen):
    title: str
    course_number: str | None
    semester: str | None
    date: str | None
    grade: str
    grade_name: str | None
    passed: bool | None
    credits: float | None
    kind: str
    status: str
    study: str | None


class ProgressPart(Frozen):
    state: str
    share: float


class StudyProgress(Frozen):
    study: str
    degree: str
    modules: tuple[ProgressPart, ...]
    exams: tuple[ProgressPart, ...]


def project_achievements(body: bytes) -> tuple[Achievement, ...]:
    """Keep grades and credits; drop record IDs, comments, subjects and upstream links."""
    try:
        response = AchievementResponse.model_validate_json(body)
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid TUMonline achievement response."
        ) from None
    achievements = []
    for item in response.resource:
        wire = item.content.achievementDto
        course = wire.cpCourseLibDto
        achievements.append(
            Achievement(
                title=course.courseTitle.value,
                course_number=course.courseNumber.courseNumber if course.courseNumber else None,
                semester=wire.semesterLibDto.shortName.value if wire.semesterLibDto else None,
                date=wire.achievementDate.value[:10] if wire.achievementDate else None,
                grade=wire.gradeDto.nameShort,
                grade_name=wire.gradeDto.name.value if wire.gradeDto.name else None,
                passed=wire.gradeDto.isPositive,
                credits=wire.credits,
                kind=wire.achievementType,
                status=wire.achievementStatusType,
                study=(
                    wire.studyBasicInfoLibDto.studyName.value if wire.studyBasicInfoLibDto else None
                ),
            )
        )
    return tuple(achievements)


def progress_parts(body: bytes) -> tuple[ProgressPart, ...]:
    try:
        bar = ProgressBar.model_validate_json(body)
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Invalid TUMonline progress response.") from None
    return tuple(
        ProgressPart(state=part.tooltip.value, share=round(part.progress, 2))
        for part in bar.barElements
    )


def read_progress(get: Get) -> tuple[StudyProgress, ...]:
    try:
        studies = StudyResponse.model_validate_json(get(STUDIES))
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Invalid TUMonline study response.") from None
    results = []
    for item in studies.resource:
        study = item.content.study
        base = f"{MY_STUDIES}/{study.studyId}/progressBar"
        results.append(
            StudyProgress(
                study=study.name.value,
                degree=study.intendedDegree.value,
                modules=progress_parts(get(base + "/modules")),
                exams=progress_parts(get(base + "/exams")),
            )
        )
    return tuple(results)
