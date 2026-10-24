"""Submission previews only. Live submission requires a separately verified action boundary."""

import time
from pathlib import Path

from tum_mcp.artemis import Artemis
from tum_mcp.errors import CampusError, Code
from tum_mcp.git_ops import run_git
from tum_mcp.settings import Frozen, Provider, find_account, preferences
from tum_mcp.test_receipts import load_test_receipt
from tum_mcp.transport import API
from tum_mcp.workspace import WorkspaceReceipt, fingerprint, workflow_status


class SubmissionPreview(Frozen):
    workflow: WorkspaceReceipt
    commit: str
    branch: str
    changed_files: tuple[str, ...]
    working_tree_changes: tuple[str, ...]
    local_tests_match: bool
    deadline_status: str
    submission_policy_known: bool
    remaining_approved_attempts: int = 0
    remote_actions_enabled: bool = False
    limitations: tuple[str, ...]
    prepared_at: float


def preview(workspace: Path) -> SubmissionPreview:
    receipt = workflow_status(workspace)
    account = find_account(receipt.account_id, Provider.ARTEMIS)
    provider = Artemis(API(account))
    view = provider.exercise(receipt.course_id, receipt.exercise_id)
    participation = provider.participation(view.exercise, receipt.mode)
    if participation.id != receipt.participation_id:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Participation changed since workspace preparation."
        )
    head = run_git(workspace, ["rev-parse", "HEAD"])
    branch = run_git(workspace, ["branch", "--show-current"])
    if (
        branch != receipt.branch
        or run_git(workspace, ["remote", "get-url", "origin"]) != receipt.repository
    ):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Repository or branch differs from the workflow receipt."
        )
    status = run_git(
        workspace, ["status", "--porcelain", "--", ".", ":(exclude).tum-mcp-workspace.json"]
    )
    committed = run_git(
        workspace,
        ["diff", "--no-ext-diff", "--no-textconv", "--name-status", receipt.base_revision, head],
    )
    matches = False
    try:
        tests = load_test_receipt(receipt)
    except CampusError as error:
        if error.code not in {Code.STALE_RESULT, Code.AUTH_REQUIRED}:
            raise
    else:
        recipes = [
            item
            for item in preferences().test_recipes
            if item.name == tests.recipe
            and item.account_id == receipt.account_id
            and item.course_id == receipt.course_id
        ]
        matches = (
            len(recipes) == 1
            and recipes[0].image == tests.image
            and recipes[0].argv == tests.command
            and recipes[0].verification_level == tests.verification_level
            and tests.verification_level == "full"
            and tests.workspace == workspace.resolve()
            and tests.exit_status == 0
            and tests.fingerprint_before == tests.fingerprint_after == fingerprint(workspace)
        )
    deadline = participation.individual_due_date or view.exercise.due_date
    deadline_status = (
        "unknown"
        if deadline is None
        else "passed"
        if deadline.timestamp() < time.time()
        else "open"
    )
    return SubmissionPreview(
        workflow=receipt,
        commit=head,
        branch=branch,
        changed_files=tuple(committed.splitlines()),
        working_tree_changes=tuple(status.splitlines()),
        local_tests_match=matches and not status,
        deadline_status=deadline_status,
        submission_policy_known=view.exercise.submission_policy is not None,
        limitations=(
            "Preview performs no commit, push, start, or server rebuild.",
            "Remote actions await verified trusted approval and host credential isolation.",
        ),
        prepared_at=time.time(),
    )
