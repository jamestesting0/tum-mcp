import json
import os
import time
from pathlib import Path
from typing import Final, Literal, assert_never
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tum_mcp.moodle.config import Paths, private_write
from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.platforms import System, system
from tum_mcp.moodle.secret_files import local_cipher, secure_directory

KEYCHAIN_SERVICE: Final = "tum-moodle-integration"


def system_keyring() -> KeyringBackend:
    try:
        backend: KeyringBackend
        match system():
            case System.MACOS:
                from keyring.backends.macOS import Keyring as MacKeyring

                backend = MacKeyring()
            case System.WINDOWS:
                from keyring.backends.Windows import WinVaultKeyring

                backend = WinVaultKeyring()
            case System.LINUX:
                from keyring.backends.SecretService import Keyring as SecretServiceKeyring

                backend = SecretServiceKeyring()
            case unreachable:
                assert_never(unreachable)
        _ = backend.priority
        return backend
    except (ImportError, RuntimeError):
        raise MoodleError(
            ErrorCode.SETUP_REQUIRED,
            "Native credential storage is unavailable. Unlock your system keyring; "
            "Linux requires a running Secret Service such as GNOME Keyring "
            "in your desktop session.",
        ) from None


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

    def __init__(self, paths: Paths, *, storage: Literal["native", "file"] | None = None) -> None:
        self.paths = paths
        self.storage = storage or os.environ.get("TUM_MOODLE_SESSION_STORAGE", "native")
        if self.storage not in {"native", "file"}:
            raise MoodleError(ErrorCode.SETUP_REQUIRED, "Choose native or file session storage.")
        self.state_root = paths.root / "local-session" if self.storage == "file" else paths.root
        if self.storage == "file":
            secure_directory(self.state_root)
        else:
            self.state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = FileLock(self.file("session.lock"))

    def file(self, name: str) -> Path:
        return self.state_root / name

    def _cipher(self, *, create: bool = False) -> Fernet:
        if self.storage == "file":
            return local_cipher(self.state_root, create=create)
        try:
            backend = system_keyring()
            key = backend.get_password(KEYCHAIN_SERVICE, str(self.paths.root))
            if key is None and create:
                key = Fernet.generate_key().decode("ascii")
                backend.set_password(KEYCHAIN_SERVICE, str(self.paths.root), key)
            if key is None:
                raise MoodleError(ErrorCode.AUTH_REQUIRED, "Sign in to TUM Moodle first.")
            return Fernet(key.encode("ascii"))
        except KeyringError:
            raise MoodleError(
                ErrorCode.SETUP_REQUIRED, "Unlock your system credential store and retry."
            ) from None

    def generation(self) -> str:
        path = self.file("generation")
        return path.read_text().strip() if path.exists() else ""

    def begin_login(self) -> str:
        with self.lock:
            generation = uuid4().hex
            private_write(self.file("generation"), generation.encode())
            return generation

    def load(self) -> Session:
        with self.lock:
            path = self.file("session.enc")
            if path.is_symlink():
                raise MoodleError(ErrorCode.SETUP_REQUIRED, "Session record cannot be a symlink.")
            if not path.exists():
                raise MoodleError(
                    ErrorCode.AUTH_REQUIRED,
                    "Run tum-mcp login in a terminal and select Moodle."
                    if self.storage == "file"
                    else "Use moodle_login to sign in.",
                )
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
                self.file("session.enc"),
                self._cipher(create=True).encrypt(session.model_dump_json().encode()),
            )

    def logout(self) -> None:
        with self.lock:
            private_write(self.file("generation"), uuid4().hex.encode())
            self.file("session.enc").unlink(missing_ok=True)
            self.file("login.json").unlink(missing_ok=True)

    def progress(self) -> LoginProgress | None:
        path = self.file("login.json")
        if not path.exists():
            return None
        try:
            return LoginProgress.model_validate_json(path.read_bytes())
        except (json.JSONDecodeError, ValidationError):
            return None

    def set_progress(self, progress: LoginProgress) -> None:
        private_write(self.file("login.json"), progress.model_dump_json().encode())

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
            message = error.message
            if (
                progress
                and progress.state == "failed"
                and progress.message
                and error.code in {ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_EXPIRED}
            ):
                message = progress.message
            return {"state": error.code.value, "message": message}
        return {"state": "SAVED_SESSION", "last_verified_at": session.verified_at}
