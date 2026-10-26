"""Anonymous course-to-curriculum positions, independent of student progress."""

from typing import Literal

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.tumonline.courses import Text
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.tumonline.transport import MAX_RESPONSE, permitted_credential

MAX_OUTPUT = 30_000


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class StudyName(Wire):
    name: Text
    curriculumVersionIdentification: str = Field(max_length=200)


class PathElement(Wire):
    name: Text


class PositionPath(Wire):
    path: tuple[PathElement, ...] = Field(max_length=40)


class PositionWire(Wire):
    studyNameInfoDto: StudyName
    curriculumPositionPathDto: PositionPath


class Content(Wire):
    coCurriculumPositionDto: PositionWire


class Resource(Wire):
    content: Content


class Response(Wire):
    resource: tuple[Resource, ...] = Field(max_length=2000)


class CurriculumPosition(Frozen):
    program: str
    version: str
    path: tuple[str, ...]


class PositionPage(Frozen):
    positions: tuple[CurriculumPosition, ...]
    next_offset: int | None
    coverage_status: Literal["partial"] = "partial"


class PublicCurriculum:
    """Read only public course placements; no student identity is sent upstream."""

    def __init__(
        self, policies: PolicyStore, transport: httpx2.BaseTransport | None = None
    ) -> None:
        self.policies = policies
        self.transport = transport

    def list(self, account_id: str, course_id: int, *, offset: int, limit: int) -> PositionPage:
        if course_id < 1 or offset < 0 or not 1 <= limit <= 100:
            raise CampusError(Code.SCOPE_DENIED, "Invalid curriculum page bounds.")
        policy = self.policies.read(account_id)
        if not policy.allows(Scope.STUDIES_COURSES):
            raise CampusError(Code.SCOPE_DENIED, "TUMonline studies and courses are disabled.")
        account = AccountRef(account_id=account_id)
        vault = Vault()
        credential = permitted_credential(vault, account)
        url = (
            "https://campus.tum.de/tumonline/ee/rest/slc.cm.curriculumposition/positions/"
            f"{course_id}/course/allCurriculumPositions"
        )
        if self.policies.read(account_id) != policy:
            raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")
        try:
            with httpx2.Client(
                transport=self.transport,
                timeout=httpx2.Timeout(20, connect=5),
                follow_redirects=False,
                headers={"Accept": "application/json"},
            ) as client:
                with client.stream("GET", url) as response:
                    if response.status_code == 429:
                        raise CampusError(Code.RATE_LIMITED, "TUMonline rate limit; retry later.")
                    if response.status_code != 200:
                        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "TUMonline read failed.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE:
                            raise CampusError(
                                Code.INVALID_RESPONSE, "TUMonline response too large."
                            )
                        body.extend(chunk)
        except httpx2.HTTPError:
            raise CampusError(Code.OFFLINE, "TUMonline request failed.") from None
        try:
            wire = Response.model_validate_json(bytes(body))
        except ValidationError:
            raise CampusError(Code.INVALID_RESPONSE, "Invalid curriculum response.") from None
        positions: list[CurriculumPosition] = []
        output_bytes = 0
        for item in wire.resource[offset : offset + limit]:
            position = CurriculumPosition(
                program=item.content.coCurriculumPositionDto.studyNameInfoDto.name.value,
                version=item.content.coCurriculumPositionDto.studyNameInfoDto.curriculumVersionIdentification,
                path=tuple(
                    node.name.value
                    for node in item.content.coCurriculumPositionDto.curriculumPositionPathDto.path
                ),
            )
            size = len(position.model_dump_json().encode("utf-8")) + 1
            if size > MAX_OUTPUT:
                raise CampusError(Code.INVALID_RESPONSE, "Curriculum item exceeds output limit.")
            if output_bytes + size > MAX_OUTPUT:
                break
            positions.append(position)
            output_bytes += size
        if self.policies.read(account_id) != policy:
            raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")
        if vault.load(account).generation != credential.generation:
            raise CampusError(Code.STALE_RESULT, "TUMonline session changed; retry.")
        end = offset + len(positions)
        return PositionPage(
            positions=tuple(positions),
            next_offset=end if positions and end < len(wire.resource) else None,
        )
