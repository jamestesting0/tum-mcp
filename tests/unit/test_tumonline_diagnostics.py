from pathlib import Path

import pytest

from tum_mcp.credentials import Vault
from tum_mcp.tumonline.diagnostics import connection_checks
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.ui import State

ACCOUNT = "a" * 64


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))


def test_missing_tumonline_is_reported_without_creating_any_files(tmp_path: Path) -> None:
    checks = connection_checks()
    assert [(item.label, item.state) for item in checks] == [("TUMonline", State.UNCONFIGURED)]
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("allowed", [True, False])
def test_saved_session_obeys_policy_without_reading_secrets_or_claiming_live_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allowed: bool,
) -> None:
    policies = PolicyStore()
    policies.create(ACCOUNT)
    if not allowed:
        policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
    folder = tmp_path / "data/credentials/local"
    folder.mkdir(parents=True)
    (folder / f"{ACCOUNT}.enc").write_bytes(b"synthetic-encrypted-marker")
    (folder / "session.key").write_bytes(b"synthetic-key-marker")
    monkeypatch.setattr(
        Vault, "load", lambda *args: pytest.fail("Local diagnostics cannot read secrets")
    )
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    checks = connection_checks(live=not allowed)
    assert checks[0].state == (State.CONFIGURED if allowed else State.DISABLED)
    assert ACCOUNT not in checks[0].detail
    assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == before


def test_corrupt_policy_stays_visible_as_a_failure_and_is_not_replaced(tmp_path: Path) -> None:
    folder = tmp_path / "config/tumonline"
    folder.mkdir(parents=True)
    path = folder / f"{ACCOUNT}.json"
    path.write_text("invalid", encoding="utf-8")
    assert connection_checks()[0].state == State.FAILED
    assert path.read_text() == "invalid"


def test_read_only_snapshot_cannot_follow_a_policy_directory_symlink(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    try:
        (config / "tumonline").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks require platform privileges.")
    assert connection_checks()[0].state == State.FAILED
    assert not tuple(target.iterdir())
