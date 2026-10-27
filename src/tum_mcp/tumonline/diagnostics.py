"""Read-only local TUMonline connection and permission diagnostics."""

from tum_mcp.diagnostics import Check
from tum_mcp.errors import CampusError
from tum_mcp.settings import data_path
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.ui import State


def connection_checks(*, live: bool = False) -> tuple[Check, ...]:
    try:
        policies = PolicyStore.snapshot()
    except (CampusError, OSError):
        return (
            Check(
                label="TUMonline",
                state=State.FAILED,
                detail="Invalid local policy. Review TUMonline permissions locally.",
            ),
        )
    if not policies:
        return (
            Check(
                label="TUMonline",
                state=State.UNCONFIGURED,
                detail="No account configured. Run tum-mcp login.",
            ),
        )
    checks = []
    for index, policy in enumerate(policies, 1):
        label = "TUMonline" + (f" {index}" if len(policies) > 1 else "")
        credentials = data_path() / "credentials/local"
        saved = (credentials / f"{policy.account_id}.enc").is_file() and (
            credentials / "session.key"
        ).is_file()
        state = State.CONFIGURED if saved else State.ACTION
        detail = (
            "Session saved; not live verified." if saved else "Session missing. Run tum-mcp login."
        )
        allowed = policy.allows(Scope.STUDIES_COURSES)
        if not allowed:
            state = State.DISABLED if saved else state
            detail += " Studies and courses are disabled by policy."
        else:
            detail += " Studies and courses allowed."
        if live and saved and allowed:
            from tum_mcp.tumonline.study_service import StudyService

            try:
                StudyService().verify(policy.account_id)
                state = State.READY
                detail = "Identity verified. Studies and courses allowed."
            except CampusError as error:
                state, detail = State.ACTION, error.message
        detail += " Grades and progress unavailable."
        checks.append(Check(label=label, state=state, detail=detail))
    return tuple(checks)
