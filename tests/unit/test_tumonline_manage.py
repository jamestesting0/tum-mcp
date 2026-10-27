from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.tumonline.policy import PolicyStore, Scope

ACCOUNT = "a" * 64


def test_manager_displays_default_permissions_and_unavailable_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    PolicyStore().create(ACCOUNT)
    result = CliRunner().invoke(app, ["manage", "tumonline", "--account", ACCOUNT, "--show"])
    assert result.exit_code == 0, result.output
    assert "Studies and courses" in result.output
    assert "Grades and progress" in result.output
    assert "Unavailable" in result.output
    assert "other providers" in result.output.lower()


def test_manager_with_no_account_does_not_claim_a_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    result = CliRunner().invoke(app, ["manage", "tumonline", "--show"])
    assert result.exit_code == 0
    assert "no tumonline policy" in result.output.lower()


def test_atomic_policy_update_rejects_stale_revision(tmp_path: Path) -> None:
    policies = PolicyStore(tmp_path)
    original = policies.create(ACCOUNT)
    policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
    with pytest.raises(CampusError, match="changed"):
        policies.save_scopes(original, frozenset({Scope.STUDIES_COURSES}))
    assert not policies.read(ACCOUNT).allowed


def test_interactive_manager_can_revoke_studies_without_enabling_other_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.tumonline import manage

    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    monkeypatch.setattr(manage, "interactive_terminal", lambda: True)
    monkeypatch.setattr(manage, "choose_studies", lambda current: False)
    result = CliRunner().invoke(app, ["manage", "tumonline", "--account", ACCOUNT])
    assert result.exit_code == 0, result.output
    assert not policies.read(ACCOUNT).allowed


def test_cancelled_manager_leaves_policy_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.tumonline import manage

    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    original = policies.create(ACCOUNT)
    monkeypatch.setattr(manage, "interactive_terminal", lambda: True)
    monkeypatch.setattr(manage, "choose_studies", lambda current: None)
    result = CliRunner().invoke(app, ["manage", "tumonline", "--account", ACCOUNT])
    assert result.exit_code == 0, result.output
    assert policies.read(ACCOUNT) == original


def test_manager_preserves_previously_configured_unavailable_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.tumonline import manage

    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    policies.set_scope(ACCOUNT, Scope.EXAMS, True)
    monkeypatch.setattr(manage, "interactive_terminal", lambda: True)
    monkeypatch.setattr(manage, "choose_studies", lambda current: False)
    result = CliRunner().invoke(app, ["manage", "tumonline"])
    assert result.exit_code == 0, result.output
    assert policies.read(ACCOUNT).allowed == frozenset({Scope.EXAMS})


def test_noninteractive_manager_cannot_modify_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.tumonline import manage

    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    original = PolicyStore().create(ACCOUNT)
    monkeypatch.setattr(manage, "interactive_terminal", lambda: False)
    result = CliRunner().invoke(app, ["manage", "tumonline", "--account", ACCOUNT])
    assert isinstance(result.exception, CampusError)
    assert result.exception.code.value == "ACTION_REQUIRED"
    assert PolicyStore().read(ACCOUNT) == original


def test_local_disconnect_preserves_policy_and_does_not_touch_other_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.credentials import Credential, Vault
    from tum_mcp.moodle.auth import Cookie
    from tum_mcp.tumonline.identity import AccountRef

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    policy = PolicyStore().create(ACCOUNT)
    account = AccountRef(account_id=ACCOUNT)
    Vault().save(
        account,
        Credential(
            account_id=ACCOUNT,
            authentication="browser_session",
            cookies=(Cookie(name="session", value="synthetic", domain="campus.tum.de"),),
        ),
    )
    result = CliRunner().invoke(app, ["manage", "tumonline", "--account", ACCOUNT, "--disconnect"])
    assert result.exit_code == 0, result.output
    assert PolicyStore().read(ACCOUNT) == policy
    with pytest.raises(CampusError, match="AUTH_REQUIRED"):
        Vault().load(account)


@pytest.mark.parametrize("policy_state", ["missing", "corrupt"])
def test_disconnect_with_unreadable_policy_removes_only_the_target_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy_state: str
) -> None:
    from tum_mcp.credentials import Credential, Vault
    from tum_mcp.moodle.auth import Cookie
    from tum_mcp.tumonline.identity import AccountRef

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    target = AccountRef(account_id=ACCOUNT)
    other = AccountRef(account_id="b" * 64)
    vault = Vault()
    for account in (target, other):
        vault.save(
            account,
            Credential(
                account_id=account.id,
                authentication="browser_session",
                cookies=(Cookie(name="session", value="synthetic", domain="campus.tum.de"),),
            ),
        )
    policy_path = policies.root / f"{ACCOUNT}.json"
    if policy_state == "missing":
        policy_path.unlink()
    else:
        policy_path.write_text("{corrupt", encoding="utf-8")
    result = CliRunner().invoke(app, ["manage", "tumonline", "--account", ACCOUNT, "--disconnect"])
    assert result.exit_code == 0, result.output
    with pytest.raises(CampusError, match="AUTH_REQUIRED"):
        vault.load(target)
    assert vault.load(other).account_id == other.id
    if policy_state == "corrupt":
        assert policy_path.read_text(encoding="utf-8") == "{corrupt"


def test_targeted_disconnect_cannot_remove_other_provider_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.credentials import Credential, Vault
    from tum_mcp.moodle.auth import Cookie
    from tum_mcp.settings import ARTEMIS, Account, Provider

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    other = Account(provider=Provider.ARTEMIS, origin=ARTEMIS, principal="synthetic-student")
    vault = Vault()
    vault.save(
        other,
        Credential(
            account_id=other.id,
            authentication="browser_session",
            cookies=(Cookie(name="session", value="synthetic", domain="artemis.tum.de"),),
        ),
    )
    result = CliRunner().invoke(app, ["manage", "tumonline", "--account", other.id, "--disconnect"])
    assert isinstance(result.exception, CampusError)
    assert vault.load(other).account_id == other.id
