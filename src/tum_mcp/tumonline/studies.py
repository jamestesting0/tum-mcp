"""Minimal projection of TUMonline study names and degrees."""

from pydantic import ConfigDict, Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.tumonline.courses import Text


class Wire(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class StudyWire(Wire):
    name: Text
    intendedDegree: Text


class StudyContent(Wire):
    study: StudyWire = Field(alias="CmStudyInfoDto")


class StudyResource(Wire):
    content: StudyContent


class StudyResponse(Wire):
    resource: tuple[StudyResource, ...] = Field(max_length=100)


class Study(Frozen):
    name: str
    degree: str
    source_link: str = "https://campus.tum.de/tumonline/ee/ui/ca2/app/desktop/"


def project_studies(body: bytes) -> tuple[Study, ...]:
    """Project degree names without statuses, grades, arbitrary links or raw IDs."""
    try:
        response = StudyResponse.model_validate_json(body)
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Invalid TUMonline study response.") from None
    return tuple(
        Study(name=item.content.study.name.value, degree=item.content.study.intendedDegree.value)
        for item in response.resource
    )
