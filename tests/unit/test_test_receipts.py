from pathlib import Path

import pytest
from keyring.backend import KeyringBackend

from tum_mcp.errors import CampusError
from tum_mcp.runner import TestReceipt as Receipt
from tum_mcp.test_receipts import load_test_receipt, save_test_receipt
from tum_mcp.workspace import WorkspaceReceipt


def test_evidence_is_encrypted_and_bound_to_the_exact_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_keyring: KeyringBackend,
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    workflow = WorkspaceReceipt(
        account_id="a" * 64,
        instance_id="https://artemis.tum.de",
        course_id=77,
        exercise_id=11,
        participation_id=9,
        mode="graded",
        repository="https://artemis.tum.de/git/course/student.git",
        branch="main",
        base_revision="b" * 40,
        workspace=tmp_path / "assignment",
        prepared_at=0,
    )
    evidence = Receipt(
        account_id=workflow.account_id,
        course_id=77,
        exercise_id=11,
        participation_id=9,
        mode="graded",
        recipe="full-suite",
        command=("pytest",),
        image="fixture@sha256:" + "c" * 64,
        workspace=workflow.workspace,
        fingerprint_before="d" * 64,
        fingerprint_after="d" * 64,
        exit_status=0,
        started_at=0,
        finished_at=1,
        output_excerpt="synthetic-test-output",
        output_truncated=False,
        verification_level="full",
    )
    save_test_receipt(workflow, evidence)
    assert load_test_receipt(workflow) == evidence
    path = next((tmp_path / "workflow-state").glob("*.enc"))
    assert b"synthetic-test-output" not in path.read_bytes()
    with pytest.raises(CampusError, match="another workflow"):
        load_test_receipt(workflow.model_copy(update={"workspace": tmp_path / "other"}))
    with pytest.raises(CampusError, match="Run approved tests"):
        load_test_receipt(workflow.model_copy(update={"mode": "practice"}))
    path.write_bytes(b'{"exit_status": 0, "verification_level": "full"}')
    with pytest.raises(CampusError, match="integrity"):
        load_test_receipt(workflow)
