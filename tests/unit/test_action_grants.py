from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from keyring.backend import KeyringBackend

from tum_mcp.action_models import StartAction, action_fingerprint
from tum_mcp.approvals import Approvals
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError


@pytest.fixture
def action() -> StartAction:
    return StartAction(
        account_id="a" * 64,
        instance_id="https://artemis.tum.de",
        principal="7",
        credential_generation="generation-1",
        course_id=77,
        exercise_id=11,
        mode="graded",
        constraint_fingerprint="b" * 64,
    )


@pytest.fixture
def approvals(tmp_path: Path, memory_keyring: KeyringBackend) -> Approvals:
    return Approvals(Vault(tmp_path / "vault"), tmp_path / "actions", clock=lambda: 100)


def test_one_approval_allows_one_dispatch_and_preserves_unknown_outcome(
    approvals: Approvals,
    action: StartAction,
) -> None:
    # Given a locally issued grant for an exact target.
    approvals.issue(action)
    receipt = approvals.consume(action)
    # When an ambiguous remote request is recorded.
    approvals.dispatch(action, receipt)
    completed = approvals.finish(receipt.model_copy(update={"status": "unknown"}))
    # Then neither re-dispatch nor a replacement grant can repeat it.
    assert completed.status == "unknown"
    assert completed.finished_at == 100
    assert approvals.read(action_fingerprint(action)) == completed
    with pytest.raises(CampusError, match="already dispatched"):
        approvals.dispatch(action, receipt)
    with pytest.raises(CampusError, match="no retry"):
        approvals.consume(action)
    with pytest.raises(CampusError, match="reconcile"):
        approvals.issue(action)


@pytest.mark.parametrize(
    "change",
    [
        {"principal": "8"},
        {"mode": "practice"},
        {"exercise_id": 12},
        {"course_id": 78},
        {"credential_generation": "generation-2"},
        {"constraint_fingerprint": "c" * 64},
        {"instance_id": "https://other.invalid"},
    ],
)
def test_changed_target_cannot_use_old_grant(
    approvals: Approvals,
    action: StartAction,
    change: dict[str, str | int],
) -> None:
    # Given a single approval, changing any consequential target must require another review.
    approvals.issue(action)
    with pytest.raises(CampusError, match="exact action"):
        approvals.consume(action.model_copy(update=change))


def test_grant_expiry_is_checked_again_immediately_before_dispatch(
    approvals: Approvals,
    action: StartAction,
) -> None:
    approvals.issue(action)
    receipt = approvals.consume(action)
    approvals.clock = lambda: 281
    with pytest.raises(CampusError, match="expired"):
        approvals.dispatch(action, receipt)
    assert approvals.read(action_fingerprint(action)).status == "reserved"


def test_expired_grant_and_tampered_grant_fail_closed(
    approvals: Approvals,
    action: StartAction,
) -> None:
    approvals.issue(action)
    approvals.clock = lambda: 281
    with pytest.raises(CampusError, match="expiry"):
        approvals.consume(action)
    approvals.clock = lambda: 100
    path = approvals.root / f"{action_fingerprint(action)}.grant.enc"
    path.write_bytes(b"fabricated approval boolean: true")
    with pytest.raises(CampusError, match="integrity"):
        approvals.consume(action)


def test_fabricated_attempt_does_not_dispatch(
    approvals: Approvals,
    action: StartAction,
) -> None:
    approvals.issue(action)
    receipt = approvals.consume(action)
    with pytest.raises(CampusError, match="changed"):
        approvals.dispatch(action, receipt.model_copy(update={"attempt_id": "fabricated"}))
    assert approvals.read(action_fingerprint(action)).status == "reserved"


def test_copying_valid_receipt_to_another_action_cannot_authorize_it(
    approvals: Approvals,
    action: StartAction,
) -> None:
    approvals.issue(action)
    receipt = approvals.consume(action)
    other = action.model_copy(update={"exercise_id": 12})
    original = approvals.root / f"{action_fingerprint(action)}.receipt.enc"
    copied = approvals.root / f"{action_fingerprint(other)}.receipt.enc"
    copied.write_bytes(original.read_bytes())
    with pytest.raises(CampusError, match="target"):
        approvals.dispatch(other, receipt)


def test_parallel_consumers_cannot_spend_the_same_grant_twice(
    approvals: Approvals,
    action: StartAction,
) -> None:
    approvals.issue(action)

    def consume() -> str:
        try:
            return approvals.consume(action).status
        except CampusError:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == ["denied", "reserved"]


def test_receipts_are_authenticated_and_do_not_accept_path_traversal(
    approvals: Approvals,
    action: StartAction,
) -> None:
    approvals.issue(action)
    approvals.consume(action)
    path = approvals.root / f"{action_fingerprint(action)}.receipt.enc"
    assert b'"principal"' not in path.read_bytes()
    path.write_bytes(b'{"status": "confirmed"}')
    with pytest.raises(CampusError, match="integrity"):
        approvals.read(action_fingerprint(action))
    with pytest.raises(CampusError, match="fingerprint"):
        approvals.read("../secret")
