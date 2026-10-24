"""Account-bound encrypted credentials; never included in tool results."""

from pathlib import Path
from typing import Final, Literal
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock
from keyring.errors import KeyringError
from pydantic import Field, SecretStr, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Account, Frozen, data_dir
from tum_moodle import auth
from tum_moodle.auth import Cookie
from tum_moodle.config import private_write

SERVICE: Final = "tum-mcp"


class RepositorySecret(Frozen):
    url: str
    username: SecretStr = Field(repr=False)
    password: SecretStr = Field(repr=False)


class Credential(Frozen):
    account_id: str
    authentication: Literal["api_key", "browser_session"] = "api_key"
    generation: str = Field(default_factory=lambda: uuid4().hex)
    username: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    cookies: tuple[Cookie, ...] = Field(default=(), repr=False, exclude=True)
    repositories: tuple[RepositorySecret, ...] = Field(default=(), repr=False, exclude=True)

    def encoded(self) -> bytes:
        # Pydantic intentionally masks SecretStr in normal serialization.
        return (
            StoredCredential(
                account_id=self.account_id,
                authentication=self.authentication,
                generation=self.generation,
                username=self.username.get_secret_value(),
                api_key=self.api_key.get_secret_value(),
                cookies=self.cookies,
                repositories=tuple(
                    StoredRepository(
                        url=item.url,
                        username=item.username.get_secret_value(),
                        password=item.password.get_secret_value(),
                    )
                    for item in self.repositories
                ),
            )
            .model_dump_json()
            .encode()
        )


class StoredCredential(Frozen):
    account_id: str
    authentication: Literal["api_key", "browser_session"] = "api_key"
    generation: str
    username: str = Field(repr=False)
    api_key: str = Field(repr=False)
    cookies: tuple[Cookie, ...] = Field(repr=False)
    repositories: tuple["StoredRepository", ...] = ()


class StoredRepository(Frozen):
    url: str
    username: str = Field(repr=False)
    password: str = Field(repr=False)


class Vault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_dir() / "credentials"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = FileLock(str(self.root / "vault.lock"))

    def cipher(self, *, create: bool = False) -> Fernet:
        with self.lock:
            return self._cipher(create=create)

    def _cipher(self, *, create: bool) -> Fernet:
        try:
            backend = auth.system_keyring()
            identity = str(self.root.resolve())
            key = backend.get_password(SERVICE, identity)
            if key is None and create:
                key = Fernet.generate_key().decode()
                backend.set_password(SERVICE, identity, key)
            if key is None:
                raise CampusError(Code.AUTH_REQUIRED, "Connect this campus account first.")
            return Fernet(key.encode())
        except KeyringError:
            raise CampusError(Code.AUTH_REQUIRED, "Unlock the native credential store.") from None

    def save(self, account: Account, credential: Credential) -> None:
        if credential.account_id != account.id:
            raise CampusError(Code.SCOPE_DENIED, "Credential principal does not match.")
        with self.lease(account), self.lock:
            self._write(account, credential)

    def _write(self, account: Account, credential: Credential) -> None:
        private_write(
            self.root / f"{account.id}.enc",
            self.cipher(create=True).encrypt(
                credential.model_copy(update={"generation": uuid4().hex}).encoded()
            ),
        )

    def lease(self, account: Account) -> FileLock:
        """Serialize effects with credential replacement/logout for this account only."""
        return FileLock(str(self.root / f"{account.id}.lease.lock"), timeout=30)

    def load(self, account: Account) -> Credential:
        with self.lock:
            path = self.root / f"{account.id}.enc"
            if not path.exists():
                raise CampusError(Code.AUTH_REQUIRED, "Connect this account with the local CLI.")
            try:
                value = Credential.model_validate_json(self.cipher().decrypt(path.read_bytes()))
            except (InvalidToken, ValidationError):
                raise CampusError(Code.AUTH_REQUIRED, "Reconnect this account.") from None
            if value.account_id != account.id:
                raise CampusError(Code.SCOPE_DENIED, "Stored credential principal does not match.")
            return value

    def logout(self, account: Account) -> None:
        with self.lease(account), self.lock:
            (self.root / f"{account.id}.enc").unlink(missing_ok=True)

    def replace_login(self, account: Account, credential: Credential) -> None:
        """Rotate the login generation while preserving this identity's Git credentials."""
        if credential.account_id != account.id:
            raise CampusError(Code.SCOPE_DENIED, "Credential principal does not match.")
        with self.lease(account), self.lock:
            path = self.root / f"{account.id}.enc"
            if path.exists():
                previous = self.load(account)
                credential = credential.model_copy(update={"repositories": previous.repositories})
            self._write(account, credential)
