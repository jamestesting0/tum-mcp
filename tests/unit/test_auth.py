from pathlib import Path

import keyring
import pytest

from tum_moodle.auth import Cookie, LoginProgress, Session, SessionStore
from tum_moodle.config import Paths
from tum_moodle.errors import MoodleError


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionStore:
    keys: dict[str, str] = {}
    monkeypatch.setattr(keyring, "get_password", lambda service, account: keys.get(account))
    monkeypatch.setattr(
        keyring, "set_password", lambda service, account, key: keys.update({account: key})
    )
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
    assert store.paths.file("session.enc").stat().st_mode & 0o777 == 0o600


def test_logout_prevents_stale_process_restoring_session(store: SessionStore) -> None:
    session = Session(generation=store.begin_login(), verified_at=1, cookies=[])
    store.save(session)
    store.logout()
    with pytest.raises(MoodleError):
        store.save(session)
    with pytest.raises(MoodleError):
        store.load()


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
