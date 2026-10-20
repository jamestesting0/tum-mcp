import json
import time
from typing import Final, Literal
from uuid import uuid4

import keyring
from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock
from keyring.backends.macOS import Keyring as MacKeyring
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tum_moodle.config import Paths, private_write
from tum_moodle.errors import ErrorCode, MoodleError

KEYCHAIN_SERVICE: Final = "tum-moodle-integration"


class Cookie(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    name: str
    value: str = Field(repr=False)
    domain: str
    path: str = "/"
    expires: float = -1
    httpOnly: bool = True
    secure: bool = True
    sameSite: Literal["Strict", "Lax", "None"] = "Lax"


class Session(BaseModel):
    model_config = ConfigDict(frozen=True)
    generation: str
    cookies: list[Cookie] = Field(repr=False)
    verified_at: float


class LoginProgress(BaseModel):
    model_config = ConfigDict(frozen=True)
    operation_id: str
    state: Literal["authenticating", "connected", "cancelled", "failed"]
    started_at: float
    message: str = ""


class SessionStore:
    """Serialize updates under a lock; never expose encrypted or clear session data."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.lock = FileLock(paths.file("session.lock"))

    def _cipher(self, *, create: bool = False) -> Fernet:
        if not isinstance(keyring.get_keyring(), MacKeyring):
            raise MoodleError(
                ErrorCode.SETUP_REQUIRED, "Use the macOS Keychain backend for sessions."
            )
        try:
            key = keyring.get_password(KEYCHAIN_SERVICE, str(self.paths.root))
            if key is None and create:
                key = Fernet.generate_key().decode("ascii")
                keyring.set_password(KEYCHAIN_SERVICE, str(self.paths.root), key)
            if key is None:
                raise MoodleError(ErrorCode.AUTH_REQUIRED, "Sign in to TUM Moodle first.")
            return Fernet(key.encode("ascii"))
        except KeyringError:
            raise MoodleError(
                ErrorCode.SETUP_REQUIRED, "Unlock macOS Keychain and retry."
            ) from None

    def generation(self) -> str:
        path = self.paths.file("generation")
        return path.read_text().strip() if path.exists() else ""

    def begin_login(self) -> str:
        with self.lock:
            generation = uuid4().hex
            private_write(self.paths.file("generation"), generation.encode())
            return generation

    def load(self) -> Session:
        with self.lock:
            path = self.paths.file("session.enc")
            if not path.exists():
                raise MoodleError(ErrorCode.AUTH_REQUIRED, "Use moodle_login to sign in.")
            try:
                session = Session.model_validate_json(self._cipher().decrypt(path.read_bytes()))
            except (InvalidToken, ValidationError):
                raise MoodleError(ErrorCode.SESSION_EXPIRED, "Reconnect to TUM Moodle.") from None
            if session.generation != self.generation():
                raise MoodleError(ErrorCode.SESSION_EXPIRED, "Reconnect to TUM Moodle.")
            return session

    def save(self, session: Session) -> None:
        with self.lock:
            if session.generation != self.generation():
                raise MoodleError(ErrorCode.SESSION_EXPIRED, "The session was disconnected.")
            private_write(
                self.paths.file("session.enc"),
                self._cipher(create=True).encrypt(session.model_dump_json().encode()),
            )

    def logout(self) -> None:
        with self.lock:
            private_write(self.paths.file("generation"), uuid4().hex.encode())
            self.paths.file("session.enc").unlink(missing_ok=True)
            self.paths.file("login.json").unlink(missing_ok=True)

    def progress(self) -> LoginProgress | None:
        path = self.paths.file("login.json")
        if not path.exists():
            return None
        try:
            return LoginProgress.model_validate_json(path.read_bytes())
        except (json.JSONDecodeError, ValidationError):
            return None

    def set_progress(self, progress: LoginProgress) -> None:
        private_write(self.paths.file("login.json"), progress.model_dump_json().encode())

    def status(self) -> dict[str, str | float | None]:
        progress = self.progress()
        if (
            progress
            and progress.state == "authenticating"
            and time.time() - progress.started_at < 600
        ):
            return {"state": "AUTHENTICATING", "operation_id": progress.operation_id}
        try:
            session = self.load()
        except MoodleError as error:
            return {"state": error.code.value, "message": error.message}
        return {"state": "SAVED_SESSION", "last_verified_at": session.verified_at}
