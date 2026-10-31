"""Read-only local TUMonline connection and permission diagnostics."""

from tum_mcp.diagnostics import Check, session_check
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
        check = Check(label=label, state=state, detail=detail)
        if saved and allowed:
            from tum_mcp.tumonline.study_service import StudyService

            def verify_account(account_id: str = policy.account_id) -> None:
                StudyService().verify(account_id)

            check = session_check(
                check,
                session=credentials / f"{policy.account_id}.enc",
                key=credentials / "session.key",
                live=live,
                verify=verify_account,
                verified_detail="Identity verified. Studies and courses allowed.",
            )
        checks.append(
            check.model_copy(update={"detail": check.detail + " Grades and progress unavailable."})
        )
    return tuple(checks)
