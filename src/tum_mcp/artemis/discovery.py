"""Course discovery with optional access to the student history listing."""

from tum_mcp.artemis.client import Artemis
from tum_mcp.artemis.models import CourseDirectory
from tum_mcp.settings import Provider, find_account
from tum_mcp.transport import API


def artemis_list_courses(account_id: str, include_past: bool = False) -> CourseDirectory:
    """List active courses; include_past=true adds accessible past semesters, active first."""
    courses = Artemis(API(find_account(account_id, Provider.ARTEMIS))).courses(
        include_past=include_past
    )
    return CourseDirectory(account_id=account_id, courses=courses.root)
