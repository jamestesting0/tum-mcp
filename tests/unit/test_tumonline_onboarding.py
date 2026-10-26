from pathlib import Path

import pytest
from pydantic import SecretStr

from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.auth import ResumedSession
from tum_mcp.tumonline.identity import account_for_subject
from tum_mcp.tumonline.onboarding import begin_login, save_connection
from tum_mcp.tumonline.policy import PolicyStore, Scope

ACCOUNT = account_for_subject("synthetic-student")
COOKIE = Cookie(name="session", value="synthetic-cookie", domain="campus.tum.de")
SESSION = ResumedSession(account=ACCOUNT, token=SecretStr("synthetic-token"), cookies=(COOKIE,))


def test_onboarding_saves_only_service_cookie_and_default_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    account = save_connection(SESSION, attempt=begin_login())
    assert account == ACCOUNT
    assert PolicyStore().read(account.id).allowed == frozenset({Scope.STUDIES_COURSES})
    saved = Vault().load(account)
    assert saved.cookies == (COOKIE,)
    assert b"synthetic-token" not in Vault().record_path(account).read_bytes()
    assert "synthetic-token" not in saved.model_dump_json()


def test_reconnect_preserves_revoked_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    save_connection(SESSION, attempt=begin_login())
    PolicyStore().set_scope(ACCOUNT.id, Scope.STUDIES_COURSES, False)
    save_connection(SESSION, attempt=begin_login())
    assert not PolicyStore().read(ACCOUNT.id).allows(Scope.STUDIES_COURSES)


def test_missing_policy_with_existing_credential_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    save_connection(SESSION, attempt=begin_login())
    (PolicyStore().root / f"{ACCOUNT.id}.json").unlink()
    with pytest.raises(CampusError, match="policy"):
        save_connection(SESSION, attempt=begin_login())


def test_connect_context_verifies_same_identity_twice_and_discards_idp_cookies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock

    from tum_mcp.tumonline import auth
    from tum_mcp.tumonline.onboarding import connect_context

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    context = MagicMock()
    context.cookies.return_value = [
        {"name": "session", "value": "synthetic-cookie", "domain": "campus.tum.de", "secure": True},
        {"name": "identity", "value": "synthetic-idp", "domain": "login.tum.de", "secure": True},
    ]
    calls = []

    def refresh(cookies, transport=None, *, expected=None):
        calls.append((cookies, expected))
        return SESSION

    monkeypatch.setattr(auth, "resume_session", refresh)
    assert connect_context(context, begin_login()) == ACCOUNT
    assert len(calls) == 2
    assert calls[0][0] == (COOKIE,)
    assert calls[1][1] == ACCOUNT
    assert Vault().load(ACCOUNT).cookies == (COOKIE,)


def test_connect_context_waits_for_login_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock

    from tum_mcp.tumonline.onboarding import connect_context

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    context = MagicMock()
    context.cookies.return_value = []
    assert connect_context(context, begin_login()) is None
    assert not (tmp_path / "credentials").exists()


def test_disconnect_invalidates_an_inflight_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.tumonline.onboarding import begin_login, disconnect

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    pending = begin_login()
    disconnect(ACCOUNT)
    with pytest.raises(CampusError, match="STALE_RESULT"):
        save_connection(SESSION, attempt=pending)
    with pytest.raises(CampusError, match="AUTH_REQUIRED"):
        Vault().load(ACCOUNT)


def test_forgetting_credentials_invalidates_an_inflight_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.removal import _forget_local_credentials

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    pending = begin_login()
    _forget_local_credentials()
    with pytest.raises(CampusError, match="STALE_RESULT"):
        save_connection(SESSION, attempt=pending)
