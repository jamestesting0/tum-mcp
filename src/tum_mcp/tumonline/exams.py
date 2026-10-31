"""Projections of the student's registered exams and searchable exam offers."""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.tumonline.auth import Get
from tum_mcp.tumonline.courses import Text

REGISTERED: Final = "/tumonline/ee/rest/slc.xm.exr/registered-exams"
OFFERS: Final = "/tumonline/ee/rest/slc.xm.exr/exExamOffer"


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Instant(Wire):
    value: str = Field(max_length=40)


class Appointment(Wire):
    displayName: str = Field(max_length=500)


class OfferWire(Wire):
    courseName: Text
    displayCourseNumber: str | None = Field(default=None, max_length=200)
    courseSemesterShortName: Text | None = None
    examType: Text | None = None
    examDate: Instant | None = None
    examStart: Instant | None = None
    examEnd: Instant | None = None
    appointments: tuple[Appointment, ...] = Field(default=(), max_length=50)
    registrationDateStart: Instant | None = None
    registrationDateEnd: Instant | None = None
    deRegistrationEnd: Instant | None = None
    registrationState: str | None = Field(default=None, max_length=60)


class OfferList(Wire):
    examOffers: tuple[OfferWire, ...] = Field(max_length=1000)
    totalCount: int = Field(ge=0, strict=True)


class Exam(Frozen):
    course: str
    course_number: str | None
    semester: str | None
    kind: str | None
    date: str | None
    start: str | None
    end: str | None
    rooms: tuple[str, ...]
    registration_start: str | None
    registration_end: str | None
    deregistration_end: str | None
    registration_state: str | None


class ExamPage(Frozen):
    exams: tuple[Exam, ...]
    coverage_status: Literal["complete", "partial"]
    next_offset: int | None


def value(instant: Instant | Text | None) -> str | None:
    return instant.value if instant is not None else None


def project_exams(body: bytes) -> tuple[tuple[Exam, ...], int]:
    """Keep dates, rooms and registration windows; drop examiner names, IDs and links."""
    try:
        wire = OfferList.model_validate_json(body)
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Invalid TUMonline exam response.") from None
    exams = tuple(
        Exam(
            course=offer.courseName.value,
            course_number=offer.displayCourseNumber,
            semester=value(offer.courseSemesterShortName),
            kind=value(offer.examType),
            date=value(offer.examDate),
            start=value(offer.examStart),
            end=value(offer.examEnd),
            rooms=tuple(item.displayName for item in offer.appointments),
            registration_start=value(offer.registrationDateStart),
            registration_end=value(offer.registrationDateEnd),
            deregistration_end=value(offer.deRegistrationEnd),
            registration_state=offer.registrationState,
        )
        for offer in wire.examOffers
    )
    return exams, wire.totalCount


def read_registered(get: Get) -> tuple[Exam, ...]:
    exams, _ = project_exams(get(REGISTERED))
    return exams


def read_offers(get: Get, *, offset: int, limit: int, query: str | None) -> ExamPage:
    # TUMonline ignores $top unless $skip is also present, then returns every offer (~20 MB).
    params = {"$skip": str(offset), "$top": str(limit)}
    if query is not None:
        params["$filter"] = "q-likeI=" + query
    exams, total = project_exams(get(OFFERS, params))
    if len(exams) > limit or offset + len(exams) > total:
        raise CampusError(Code.INVALID_RESPONSE, "Exam page metadata is inconsistent.")
    end = offset + len(exams)
    complete = end >= total
    return ExamPage(
        exams=exams,
        coverage_status="complete" if complete else "partial",
        next_offset=end if exams and not complete else None,
    )
