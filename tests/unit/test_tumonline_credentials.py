from pathlib import Path

import pytest

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.identity import account_for_subject


def test_tumonline_account_reuses_encrypted_campus_vault(tmp_path: Path) -> None:
    account = account_for_subject("synthetic-student-id")
    vault = Vault(tmp_path)
    cookie = Cookie(name="session", value="synthetic-secret", domain="campus.tum.de")
    credential = Credential(
        account_id=account.id, authentication="browser_session", cookies=(cookie,)
    )
    vault.save(account, credential)
    assert vault.load(account).cookies == (cookie,)
    assert b"synthetic-secret" not in vault.record_path(account).read_bytes()
    assert "synthetic-secret" not in repr(vault.load(account))
    with pytest.raises(CampusError):
        vault.load(account_for_subject("other-synthetic-student"))


def test_account_id_is_stable_and_never_contains_raw_identity() -> None:
    first = account_for_subject("synthetic-student-id")
    assert first == account_for_subject("synthetic-student-id")
    assert first != account_for_subject("different-student")
    assert len(first.id) == 64
    assert "synthetic-student-id" not in first.model_dump_json()


def test_vault_refresh_updates_rotated_cookies_under_account_lease(tmp_path: Path) -> None:
    account = account_for_subject("synthetic-student")
    vault = Vault(tmp_path)
    first = Cookie(name="session", value="synthetic-old", domain="campus.tum.de")
    rotated = Cookie(name="session", value="synthetic-new", domain="campus.tum.de")
    vault.save(
        account,
        Credential(account_id=account.id, authentication="browser_session", cookies=(first,)),
    )
    before = vault.load(account)

    def refresh(current, checkpoint):
        assert current.generation == before.generation
        return (rotated,), "synthetic-result"

    saved, result = vault.refresh_browser_session(account, refresh)
    assert result == "synthetic-result"
    assert saved.cookies == (rotated,)
    assert saved.generation != before.generation
    assert vault.load(account) == saved
    assert b"synthetic-new" not in vault.record_path(account).read_bytes()


def test_failed_refresh_preserves_saved_credential(tmp_path: Path) -> None:
    account = account_for_subject("synthetic-student")
    vault = Vault(tmp_path)
    cookie = Cookie(name="session", value="synthetic-old", domain="campus.tum.de")
    vault.save(
        account,
        Credential(account_id=account.id, authentication="browser_session", cookies=(cookie,)),
    )
    before = vault.load(account)

    def fail(current, checkpoint):
        raise CampusError("AUTH_REQUIRED", "synthetic failure")

    with pytest.raises(CampusError):
        vault.refresh_browser_session(account, fail)
    assert vault.load(account) == before
