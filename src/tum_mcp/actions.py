"""Dormant remote executor. Release gate and one-use approval both fail closed."""

from filelock import FileLock

from tum_mcp.action_models import ActionReceipt, ActionReview, StartAction, SubmitAction
from tum_mcp.action_preflight import Preflight
from tum_mcp.approvals import Approvals
from tum_mcp.artemis import Artemis
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.git_ops import run_git
from tum_mcp.remote_gate import require_verified_boundary
from tum_mcp.settings import Account, Provider, config_dir, find_account
from tum_mcp.transport import API


def execute(review: ActionReview) -> ActionReceipt:
    """Use an existing exact grant once; never treat model-supplied text as consent."""
    require_verified_boundary()
    action = review.action
    vault = Vault()
    account = find_account(action.account_id, Provider.ARTEMIS)
    # Serialize a credential/scope revocation with the final preflight and effect.
    with FileLock(str(config_dir() / "preferences.lock")), vault.lease(account):
        account = find_account(action.account_id, Provider.ARTEMIS)
        provider = Artemis(API(account, vault.load(account)))
        preflight = Preflight(provider)
        current = (
            preflight.start(action.course_id, action.exercise_id, action.mode)
            if isinstance(action, StartAction)
            else preflight.submit(action.workspace)
        )
        if current.action != action:
            raise CampusError(
                Code.SCOPE_DENIED, "Action changed since approval; no attempt was made."
            )
        approvals = Approvals(vault)
        receipt = approvals.consume(action)
        approvals.dispatch(action, receipt)
        try:
            if isinstance(action, StartAction):
                provider.api._start_once(action.exercise_id, practice=action.mode == "practice")
                view = provider.exercise(action.course_id, action.exercise_id)
                participation = provider.participation(view.exercise, action.mode)
                receipt = receipt.model_copy(
                    update={"participation_id": participation.id, "status": "confirmed"}
                )
            else:
                _push(action, account=account)
                receipt = receipt.model_copy(
                    update={
                        "participation_id": action.participation_id,
                        "commit": action.commit,
                        "status": "confirmed",
                    }
                )
        except (CampusError, OSError):
            return approvals.finish(
                receipt.model_copy(
                    update={
                        "status": "unknown",
                        "message": (
                            "Remote outcome unknown; inspect the exact participation/revision "
                            "manually. This attempt cannot be retried."
                        ),
                    }
                )
            )
        return approvals.finish(
            receipt.model_copy(
                update={"message": "Exact remote state confirmed; build feedback is separate."}
            )
        )


def _push(action: SubmitAction, *, account: Account) -> None:
    """An explicit URL avoids Git pushurl overrides. Never force, commit, or retry."""
    reference = f"refs/heads/{action.branch}"
    current = run_git(
        action.workspace, ["ls-remote", "--heads", action.repository, reference], account
    )
    if current == f"{action.commit}\t{reference}":
        return
    run_git(
        action.workspace,
        ["push", "--porcelain", action.repository, f"{action.commit}:{reference}"],
        account,
    )
    current = run_git(
        action.workspace, ["ls-remote", "--heads", action.repository, reference], account
    )
    if current != f"{action.commit}\t{reference}":
        raise CampusError(Code.STALE_RESULT, "Remote revision is not confirmed.")
