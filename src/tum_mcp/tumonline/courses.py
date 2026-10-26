"""Minimal projections of TUMonline's observed public course listing."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen


def search_query(value: str | None) -> str | None:
    """Restrict the portal's matrix-filter grammar to literal search terms."""
    if value is None:
        return None
    value = value.strip()
    if not 2 <= len(value) <= 80 or not re.fullmatch(r"[\w .+/-]+", value):
        raise CampusError(Code.SCOPE_DENIED, "Invalid TUMonline course search.")
    return value


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
        if not wire.courses and offset < wire.totalCount:
            raise CampusError(Code.OFFLINE, "TUMonline returned an incomplete page; retry.")
        courses: list[Course] = []
        size = 256
        for item in wire.courses:
            course = Course(
                id=item.id,
                number=item.courseNumber.databaseValue,
                title=item.courseTitle.value,
                term=item.semesterDto.semesterDesignation.value,
                kind=item.courseTypeDto.courseTypeShortName.value,
                source_link="https://campus.tum.de/tumonline/ee/ui/ca2/app/desktop/",
            )
            cost = len(course.model_dump_json().encode()) + 1
            if size + cost > 30_000:
                if not courses:
                    raise CampusError(Code.INVALID_RESPONSE, "Course exceeds the output budget.")
                break
            courses.append(course)
            size += cost
        position = offset + len(courses)
        complete = position >= wire.totalCount
        return cls(
            courses=tuple(courses),
            coverage_status="complete" if complete else "partial",
            next_offset=position if courses and not complete else None,
        )
