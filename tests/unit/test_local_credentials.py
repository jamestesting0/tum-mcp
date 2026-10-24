import os
from pathlib import Path

import pytest
from keyring.backend import KeyringBackend

from tum_mcp.credentials import Credential, Vault
from tum_mcp.settings import Account, Provider
from tum_moodle import auth
from tum_moodle.auth import Cookie, Session, SessionStore
from tum_moodle.config import Paths
from tum_moodle.errors import MoodleError
from tum_moodle.secret_files import local_cipher


def no_keychain() -> KeyringBackend:
    pytest.fail("Local-file authentication must not access a native keychain.")


def test_file_backed_moodle_preserves_legacy_session_without_accessing_keychain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = tmp_path / "session.enc"
    legacy.write_bytes(b"legacy-encrypted-data-to-preserve")
    (tmp_path / "generation").write_text("legacy-generation")
    monkeypatch.setattr(auth, "system_keyring", no_keychain)
    store = SessionStore(Paths(tmp_path), storage="file")
    session = Session(
        generation=store.begin_login(),
        cookies=[
            Cookie(name="MoodleSession", value="synthetic-secret", domain="www.moodle.tum.de")
        ],
        verified_at=1,
    )
    store.save(session)
    assert store.load().cookies[0].value == "synthetic-secret"
    assert b"synthetic-secret" not in store.file("session.enc").read_bytes()
    assert legacy.read_bytes() == b"legacy-encrypted-data-to-preserve"
    assert (tmp_path / "generation").read_text() == "legacy-generation"
    store.logout()
    assert legacy.is_file()
    assert not store.file("session.enc").exists()


def test_campus_file_vault_does_not_read_or_replace_legacy_native_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = Account(
        provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="fixture"
    )
    old = tmp_path / f"{account.id}.enc"
    old.write_bytes(b"legacy-native-encrypted-session")
    monkeypatch.setattr(auth, "system_keyring", no_keychain)
    vault = Vault(tmp_path)
    vault.replace_login(account, Credential(account_id=account.id))
    assert vault.load(account).account_id == account.id
    assert old.read_bytes() == b"legacy-native-encrypted-session"
    vault.logout(account)
    assert old.is_file()


def test_local_key_is_owner_only_and_survives_an_independent_store_instance(tmp_path: Path) -> None:
    payload = local_cipher(tmp_path, create=True).encrypt(b"synthetic")
    assert local_cipher(tmp_path).decrypt(payload) == b"synthetic"
    if os.name != "nt":
        assert tmp_path.stat().st_mode & 0o777 == 0o700
        assert (tmp_path / "session.key").stat().st_mode & 0o777 == 0o600


def test_missing_key_never_invalidates_existing_encrypted_records(tmp_path: Path) -> None:
    saved = tmp_path / "saved.enc"
    saved.write_bytes(b"encrypted-data-to-preserve")
    with pytest.raises(MoodleError, match="key is missing"):
        local_cipher(tmp_path, create=True)
    assert saved.read_bytes() == b"encrypted-data-to-preserve"
    assert not (tmp_path / "session.key").exists()


def test_local_key_symlink_is_rejected_without_reading_target(tmp_path: Path) -> None:
    target = tmp_path / "private-key"
    target.write_bytes(b"do-not-read")
    try:
        (tmp_path / "session.key").symlink_to(target)
    except OSError:
        pytest.skip("This profile cannot create symlinks.")
    with pytest.raises(MoodleError, match="symlink"):
        local_cipher(tmp_path, create=True)
    assert target.read_bytes() == b"do-not-read"
