"""Validated user-owned settings; no credentials or package-relative state."""

import hashlib
import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Literal
from urllib.parse import urlsplit

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tum_mcp.errors import CampusError, Code
from tum_moodle.config import private_write
from tum_moodle.platforms import app_root

ARTEMIS: Final = "https://artemis.tum.de"
ZULIP: Final = "https://zulip.cit.tum.de"
PositiveId = Annotated[int, Field(gt=0)]


class Provider(StrEnum):
    ARTEMIS = "artemis"
    ZULIP = "zulip"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Account(Frozen):
    provider: Provider
    origin: str
    principal: str = Field(min_length=1, max_length=200)
    channels: tuple[PositiveId, ...] = ()
    private_channels: tuple[PositiveId, ...] = ()
    courses: tuple[PositiveId, ...] = ()
    sensitive_reads: bool = False
    workspace_writes: bool = False
    remote_actions: bool = False
    scope_revision: int = Field(default=0, ge=0)

    @field_validator("origin")
    @classmethod
    def canonical_origin(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port not in {None, 443}
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            raise CampusError(
                Code.SCOPE_DENIED, "An HTTPS server origin without a path is required."
            )
        return f"https://{parts.hostname.lower()}"

    @property
    def id(self) -> str:
        value = f"{self.provider}\0{self.origin}\0{self.principal}"
        return hashlib.sha256(value.encode()).hexdigest()


class CourseMapping(Frozen):
    name: str
    moodle_id: PositiveId | None = None
    artemis_account: str | None = None
    artemis_id: PositiveId | None = None
    zulip_account: str | None = None
    channel_ids: tuple[PositiveId, ...] = ()


class TestRecipe(Frozen):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    account_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    course_id: PositiveId
    image: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./:_-]*@sha256:[a-f0-9]{64}$")
    argv: tuple[str, ...] = Field(min_length=1, max_length=30)
    timeout_seconds: int = Field(default=180, ge=1, le=900)
    verification_level: Literal["targeted", "full"] = "targeted"


class Preferences(Frozen):
    schema_version: int = Field(default=1, ge=1, le=1)
    accounts: tuple[Account, ...] = ()
    mappings: tuple[CourseMapping, ...] = ()
    workspace_root: Path = Field(default_factory=lambda: Path.home() / "University")
    language: str = "en"
    catch_up_window_days: int = Field(default=7, ge=1, le=365)
    muted_topics: tuple[str, ...] = ()
    assistance_mode: str = Field(default="debug", pattern="^(explain|hints|debug|implement)$")
    max_local_iterations: int = Field(default=3, ge=1, le=20)
    test_recipes: tuple[TestRecipe, ...] = ()


def data_path() -> Path:
    return (
        Path(os.environ.get("TUM_MCP_DATA_DIR", app_root().with_name("TUMMCP")))
        .expanduser()
        .resolve()
    )


def config_path() -> Path:
    return Path(os.environ.get("TUM_MCP_CONFIG_DIR", data_path() / "config")).expanduser().resolve()


def data_dir() -> Path:
    path = data_path()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path.resolve()


def config_dir() -> Path:
    data_dir()
    path = config_path()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path.resolve()


def preferences() -> Preferences:
    path = config_dir() / "preferences.json"
    if not path.exists():
        return Preferences()
    try:
        return Preferences.model_validate_json(path.read_bytes())
    except (ValidationError, OSError):
        raise CampusError(Code.SCOPE_DENIED, "Invalid preferences; inspect them locally.") from None


def save_account(account: Account, *, preserve_scopes: bool = False) -> None:
    with FileLock(str(config_dir() / "preferences.lock")):
        current = preferences()
        previous = next((item for item in current.accounts if item.id == account.id), None)
        revision = previous.scope_revision + 1 if previous else 1
        # Reconnection must not restore scopes revoked while browser sign-in was open.
        updated = (
            previous
            if preserve_scopes and previous is not None
            else account.model_copy(update={"scope_revision": revision})
        )
        accounts = tuple(item for item in current.accounts if item.id != account.id) + (updated,)
        private_write(
            config_dir() / "preferences.json",
            current.model_copy(update={"accounts": accounts}).model_dump_json(indent=2).encode(),
        )


def find_account(account_id: str, provider: Provider) -> Account:
    for account in preferences().accounts:
        if account.id == account_id and account.provider == provider:
            return account
    raise CampusError(Code.AUTH_REQUIRED, f"Connect the {provider} account with the local CLI.")
