"""Narrow, locally scoped TUMonline tools."""

import hashlib
import time
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.server import server
from tum_mcp.settings import Frozen
from tum_mcp.tumonline.courses import Course, search_query
from tum_mcp.tumonline.curriculum import CurriculumPosition, PublicCurriculum
from tum_mcp.tumonline.cursor import CursorBinding, CursorCodec
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import Policy, PolicyStore, Scope
from tum_mcp.tumonline.studies import Study
from tum_mcp.tumonline.study_service import StudyService
from tum_mcp.tumonline.transport import PublicCourses

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
LOCAL_READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
AccountId = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Limit = Annotated[int, Field(ge=1, le=100)]
CourseId = Annotated[int, Field(gt=0, le=2147483647)]
Cursor = Annotated[str | None, Field(max_length=512)]
Search = Annotated[str | None, Field(max_length=80)]
codec = CursorCodec()


class AccountStatus(Frozen):
    policy: Policy
    connection: Literal["saved_not_live_verified", "not_connected"]


class OnlineStatus(Frozen):
    accounts: tuple[AccountStatus, ...]
    public_courses: str = "available_when_connected_and_allowed"
    studies: str = "available_when_connected_and_allowed"
    curriculum: str = "public_course_positions_only"
    academic_progress: str = "unavailable"


class CourseResult(Frozen):
    courses: tuple[Course, ...]
    coverage_status: Literal["complete", "partial"]
    next_cursor: str | None
    fetched_at: float
    untrusted_content: bool = True


class StudyResult(Frozen):
    studies: tuple[Study, ...]
    coverage_status: Literal["unknown"] = "unknown"
    fetched_at: float
    untrusted_content: bool = True


class CurriculumResult(Frozen):
    positions: tuple[CurriculumPosition, ...]
    next_cursor: str | None
    coverage_status: Literal["partial"] = "partial"
    fetched_at: float
    source_link: str = "https://campus.tum.de/tumonline/ee/ui/ca2/app/desktop/"
    untrusted_content: bool = True


@server.tool(annotations=LOCAL_READ)
def tumonline_status() -> OnlineStatus:
    """Show TUMonline policy and supported capabilities without a network request."""
    policies = PolicyStore()
    vault = Vault()
    accounts = []
    for identity in policies.accounts():
        account = AccountRef(account_id=identity)
        try:
            credential = vault.load(account)
            service_cookies = credential.authentication == "browser_session" and credential.cookies
            valid = service_cookies and all(
                cookie.domain.lstrip(".") == "campus.tum.de" and cookie.secure
                for cookie in credential.cookies
            )
            connection = "saved_not_live_verified" if valid else "not_connected"
        except CampusError as error:
            if error.code != Code.AUTH_REQUIRED:
                raise
            connection = "not_connected"
        accounts.append(AccountStatus(policy=policies.read(identity), connection=connection))
    return OnlineStatus(accounts=tuple(accounts))


@server.tool(annotations=READ)
def tumonline_list_courses(
    account_id: AccountId, cursor: Cursor = None, limit: Limit = 20, query: Search = None
) -> CourseResult:
    """Search or list public course metadata; this does not list enrollments."""
    policies = PolicyStore()
    policy = policies.read(account_id)
    if not policy.allows(Scope.STUDIES_COURSES):
        raise CampusError(Code.SCOPE_DENIED, "TUMonline studies and courses are disabled.")
    query = search_query(query)
    query_hash = hashlib.sha256(query.encode()).hexdigest() if query is not None else None
    binding = CursorBinding(
        account_id=account_id, revision=policy.revision, limit=limit, query_hash=query_hash
    )
    offset = codec.decode(cursor, binding) if cursor else 0
    page = PublicCourses(policies).list(account_id, offset=offset, limit=limit, query=query)
    if policies.read(account_id) != policy:
        raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")
    next_cursor = (
        codec.encode(binding, offset=page.next_offset) if page.next_offset is not None else None
    )
    return CourseResult(
        courses=page.courses,
        coverage_status=page.coverage_status,
        next_cursor=next_cursor,
        fetched_at=time.time(),
    )


@server.tool(annotations=READ)
def tumonline_list_studies(account_id: AccountId) -> StudyResult:
    """List study names and degrees without grades, progress, or exam information."""
    policies = PolicyStore()
    policy = policies.read(account_id)
    if not policy.allows(Scope.STUDIES_COURSES):
        raise CampusError(Code.SCOPE_DENIED, "TUMonline studies and courses are disabled.")
    studies = StudyService().list(account_id)
    if policies.read(account_id) != policy:
        raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")
    return StudyResult(studies=studies, fetched_at=time.time())


@server.tool(annotations=READ)
def tumonline_course_curriculum(
    account_id: AccountId, course_id: CourseId, cursor: Cursor = None, limit: Limit = 20
) -> CurriculumResult:
    """List public curriculum positions for a course, not the student's progress or full plan."""
    policies = PolicyStore()
    policy = policies.read(account_id)
    if not policy.allows(Scope.STUDIES_COURSES):
        raise CampusError(Code.SCOPE_DENIED, "TUMonline studies and courses are disabled.")
    binding = CursorBinding(
        account_id=account_id,
        revision=policy.revision,
        limit=limit,
        operation="curriculum_positions",
        course_id=course_id,
    )
    offset = codec.decode(cursor, binding) if cursor else 0
    page = PublicCurriculum(policies).list(account_id, course_id, offset=offset, limit=limit)
    if policies.read(account_id) != policy:
        raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")
    next_cursor = (
        codec.encode(binding, offset=page.next_offset) if page.next_offset is not None else None
    )
    return CurriculumResult(
        positions=page.positions, next_cursor=next_cursor, fetched_at=time.time()
    )
