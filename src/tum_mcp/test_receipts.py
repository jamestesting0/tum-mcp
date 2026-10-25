"""Authenticated test evidence outside student-controlled workspaces."""

from typing import TYPE_CHECKING

from cryptography.fernet import InvalidToken

from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.parsing import decode
from tum_mcp.settings import data_dir
from tum_mcp.workspace import WorkspaceReceipt

if TYPE_CHECKING:
    from tum_mcp.runner import TestReceipt


def _filename(workflow: WorkspaceReceipt) -> str:
    return (
        f"{workflow.account_id}-{workflow.course_id}-{workflow.exercise_id}-"
        f"{workflow.participation_id}-{workflow.mode}-tests.enc"
    )


def save_test_receipt(workflow: WorkspaceReceipt, receipt: "TestReceipt") -> None:
    directory = data_dir() / "workflow-state"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / _filename(workflow)
    private_write(path, Vault().cipher(create=True).encrypt(receipt.model_dump_json().encode()))


def load_test_receipt(workflow: WorkspaceReceipt) -> "TestReceipt":
    from tum_mcp.runner import TestReceipt

    path = data_dir() / "workflow-state" / _filename(workflow)
    if not path.is_file():
        raise CampusError(Code.STALE_RESULT, "Run approved tests to create authenticated evidence.")
    try:
        receipt = decode(TestReceipt, Vault().cipher().decrypt(path.read_bytes()))
    except InvalidToken:
        raise CampusError(Code.STALE_RESULT, "Test receipt integrity check failed.") from None
    if (
        receipt.account_id != workflow.account_id
        or receipt.course_id != workflow.course_id
        or receipt.exercise_id != workflow.exercise_id
        or receipt.participation_id != workflow.participation_id
        or receipt.mode != workflow.mode
        or receipt.workspace != workflow.workspace.resolve()
    ):
        raise CampusError(Code.SCOPE_DENIED, "Test receipt belongs to another workflow.")
    return receipt
