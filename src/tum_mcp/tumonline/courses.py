"""Minimal projections of TUMonline's observed public course listing."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Text(Wire):
    value: str = Field(max_length=4000)


class CourseNumber(Wire):
    databaseValue: str = Field(max_length=200)


class Term(Wire):
    semesterDesignation: Text


class CourseType(Wire):
    courseTypeShortName: Text


class CourseWire(Wire):
    id: int = Field(gt=0, strict=True)
    courseNumber: CourseNumber
    courseTitle: Text
    semesterDto: Term
    courseTypeDto: CourseType


class CourseListWire(Wire):
    courses: tuple[CourseWire, ...] = Field(max_length=100)
    totalCount: int = Field(ge=0, strict=True)


class Course(Frozen):
    id: int
    number: str
    title: str
    term: str
    kind: str
    source_link: str


class CoursePage(Frozen):
    courses: tuple[Course, ...]
    coverage_status: Literal["complete", "partial"]
    next_offset: int | None
    untrusted_content: bool = True

    @classmethod
    def from_wire(cls, body: bytes, *, offset: int, limit: int) -> "CoursePage":
        """Project allowlisted fields only; never follow upstream-supplied links."""
        if offset < 0 or not 1 <= limit <= 100:
            raise CampusError(Code.SCOPE_DENIED, "Invalid course page bounds.")
        wire = CourseListWire.model_validate_json(body)
        if len(wire.courses) > limit or offset + len(wire.courses) > wire.totalCount:
            raise CampusError(Code.INVALID_RESPONSE, "Course page metadata is inconsistent.")
        courses = tuple(
            Course(
                id=item.id,
                number=item.courseNumber.databaseValue,
                title=item.courseTitle.value,
                term=item.semesterDto.semesterDesignation.value,
                kind=item.courseTypeDto.courseTypeShortName.value,
                source_link="https://campus.tum.de/tumonline/ee/ui/ca2/app/desktop/",
            )
            for item in wire.courses
        )
        position = offset + len(courses)
        complete = position >= wire.totalCount
        return cls(
            courses=courses,
            coverage_status="complete" if complete else "partial",
            next_offset=position if courses and not complete else None,
        )
