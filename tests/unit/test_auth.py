import os
from pathlib import Path

import pytest
from keyring.backend import KeyringBackend
from keyring.errors import KeyringLocked

from tum_mcp.moodle import auth
from tum_mcp.moodle.auth import Cookie, LoginProgress, Session, SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.moodle.errors import ErrorCode, MoodleError


@pytest.fixture
def store(tmp_path: Path, memory_keyring: KeyringBackend) -> SessionStore:
    return SessionStore(Paths(tmp_path))


def test_saved_cookie_is_encrypted(store: SessionStore) -> None:
    generation = store.begin_login()
    session = Session(
        generation=generation,
        verified_at=1,
        cookies=[Cookie(name="MoodleSession", value="secret-cookie", domain="www.moodle.tum.de")],
    )
    store.save(session)
    assert b"secret-cookie" not in store.paths.file("session.enc").read_bytes()
    assert store.load() == session
    if os.name == "posix":
        assert store.paths.file("session.enc").stat().st_mode & 0o777 == 0o600


def test_logout_prevents_stale_process_restoring_session(store: SessionStore) -> None:
    session = Session(generation=store.begin_login(), verified_at=1, cookies=[])
    store.save(session)
    store.logout()
    with pytest.raises(MoodleError):
        store.save(session)
    with pytest.raises(MoodleError):
        store.load()


def test_beginning_moodle_login_invalidates_previous_live_verification(store: SessionStore) -> None:
    # Given verification for the current login generation.
    verification = store.file("session.verification.json")
    verification.write_text("previous verification")
    # When another login generation starts, before its session is saved.
    store.begin_login()
    # Then the old session cannot still appear recently verified.
    assert not verification.exists()


def test_missing_session_has_explicit_status(store: SessionStore) -> None:
    assert store.status()["state"] == "AUTH_REQUIRED"


def test_failed_login_keeps_the_actionable_failure_reason(store: SessionStore) -> None:
    store.set_progress(
        LoginProgress(
            operation_id="login-1",
            state="failed",
            started_at=0,
            message="Install Google Chrome, then retry sign-in.",
        )
    )
    assert store.status() == {
        "state": "AUTH_REQUIRED",
        "message": "Install Google Chrome, then retry sign-in.",
    }


def test_locked_keyring_has_an_actionable_error(
    store: SessionStore, monkeypatch: pytest.MonkeyPatch, memory_keyring: KeyringBackend
) -> None:
    def locked(service: str, username: str) -> str | None:
        raise KeyringLocked("locked")

    monkeypatch.setattr(memory_keyring, "get_password", locked)
    session = Session(generation=store.begin_login(), verified_at=0, cookies=[])

    with pytest.raises(MoodleError, match="SETUP_REQUIRED"):
        store.save(session)
    assert not store.paths.file("session.enc").exists()


def test_native_keyring_cannot_be_replaced_by_an_environment_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")

    try:
        backend = auth.system_keyring()
    except MoodleError as error:
        assert error.code is ErrorCode.SETUP_REQUIRED
    else:
        assert backend.__class__.__module__ in {
            "keyring.backends.macOS",
            "keyring.backends.Windows",
            "keyring.backends.SecretService",
        }
