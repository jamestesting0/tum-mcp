import shutil
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal
from uuid import uuid4

from filelock import FileLock
from pydantic import Field, ValidationError, field_validator

from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError
from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.secret_files import secure_directory
from tum_mcp.profile_cookies import cookie_file
from tum_mcp.profile_paths import (
    launch_path,
    local_path,
    managed_root,
    protect_directory,
    validate_root,
)
from tum_mcp.settings import Frozen, config_dir

ProfileDirectory = Annotated[str, Field(pattern=r"^[^/\\.:\x00-\x1f][^/\\:\x00-\x1f]*$")]


class BrowserProfile(Frozen):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    executable: str
    browser_name: str = "Browser"
    windows_host: bool = False
    root: str
    directory: ProfileDirectory = "Default"
    name: str = Field(min_length=1, max_length=80)
    managed: bool = False

    @property
    def browser(self) -> BrowserChoice:
        return BrowserChoice(self.browser_name, self.executable, self.windows_host, self)

    @field_validator("root")
    @classmethod
    def absolute_root(cls, value: str) -> str:
        if not Path(value).is_absolute() and not PureWindowsPath(value).is_absolute():
            raise ValueError("Browser data folder must be absolute.")
        return value


class BrowserPreferences(Frozen):
    schema_version: Literal[1] = 1
    profiles: tuple[BrowserProfile, ...] = ()
    last_browser: str | None = None
    last_profile: str | None = None


class ProfileInfo(Frozen, extra="ignore"):
    name: str = ""


class ProfileCache(Frozen, extra="ignore"):
    info_cache: dict[ProfileDirectory, ProfileInfo] = Field(default_factory=dict)


class LocalState(Frozen, extra="ignore"):
    profile: ProfileCache = Field(default_factory=ProfileCache)


def read_preferences() -> BrowserPreferences:
    path = config_dir() / "browsers.json"
    if not path.exists():
        return BrowserPreferences()
    try:
        return BrowserPreferences.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        raise BrowserSetupError(
            "Saved browser settings are unreadable; inspect browsers.json locally."
        ) from None


def write_preferences(value: BrowserPreferences) -> None:
    private_write(config_dir() / "browsers.json", value.model_dump_json(indent=2).encode())


def browser_choices(browsers: tuple[BrowserChoice, ...]) -> tuple[BrowserChoice, ...]:
    preferences = read_preferences()
    choices = list(browsers)
    for browser in browsers:
        for profile in preferences.profiles:
            if (
                profile.executable == browser.executable
                and local_path(browser, profile.root).is_dir()
                and (
                    profile.managed
                    or (
                        local_path(browser, profile.root) / profile.directory / "Preferences"
                    ).is_file()
                )
            ):
                choices.append(replace(browser, profile=profile))
    choices.sort(
        key=lambda item: (
            not (
                item.executable == preferences.last_browser
                and (item.profile.id if item.profile else None) == preferences.last_profile
            )
        )
    )
    return tuple(choices)


def remember_browser(browser: BrowserChoice) -> None:
    with FileLock(str(config_dir() / "browsers.lock")):
        write_preferences(
            read_preferences().model_copy(
                update={
                    "last_browser": browser.executable,
                    "last_profile": browser.profile.id if browser.profile else None,
                }
            )
        )


def profiles_in(browser: BrowserChoice, value: str) -> tuple[BrowserProfile, ...]:
    """Read profile names only; never inspect password or cookie databases."""
    root = validate_root(browser, local_path(browser, value))
    if (root / "Preferences").is_file():
        root = validate_root(browser, root.parent)
    try:
        state = LocalState.model_validate_json((root / "Local State").read_bytes())
    except (OSError, ValidationError):
        raise BrowserSetupError(
            "Choose a browser data folder containing a readable Local State file."
        ) from None
    profiles = []
    for directory, info in state.profile.info_cache.items():
        if (root / directory / "Preferences").is_file():
            profiles.append(
                BrowserProfile(
                    id=uuid4().hex,
                    executable=browser.executable,
                    browser_name=browser.name,
                    windows_host=browser.windows_host,
                    root=launch_path(browser, root),
                    directory=directory,
                    name="".join(char for char in info.name if char.isprintable()).strip()[:80]
                    or directory[:80],
                )
            )
    if not profiles:
        raise BrowserSetupError("No browser profiles were found in that folder.")
    return tuple(profiles)


def create_profile(browser: BrowserChoice, name: str) -> BrowserChoice:
    profile_id = uuid4().hex
    root = managed_root(browser) / profile_id
    protect_directory(browser, root)
    profile = BrowserProfile(
        id=profile_id,
        executable=browser.executable,
        browser_name=browser.name,
        windows_host=browser.windows_host,
        root=launch_path(browser, root),
        name=name,
        managed=True,
    )
    return register_profile(replace(browser, profile=profile))


def register_profile(browser: BrowserChoice) -> BrowserChoice:
    profile = browser.profile
    if profile is None:
        raise BrowserSetupError("Choose a saved profile to register.")
    root = validate_root(browser, local_path(browser, profile.root))
    if not root.is_dir():
        raise BrowserSetupError("The saved browser folder is missing.")
    if not profile.managed and not (root / profile.directory / "Preferences").is_file():
        raise BrowserSetupError("The selected browser profile is missing.")
    secure_directory(config_dir())
    with FileLock(str(config_dir() / "browsers.lock")):
        preferences = read_preferences()
        for previous in preferences.profiles:
            if (
                previous.executable == profile.executable
                and local_path(browser, previous.root) == root
                and previous.directory == profile.directory
            ):
                return replace(browser, profile=previous)
        write_preferences(
            preferences.model_copy(update={"profiles": (*preferences.profiles, profile)})
        )
    return browser


def rename_profile(browser: BrowserChoice, name: str) -> None:
    if browser.profile is None:
        raise BrowserSetupError("Choose a saved profile to rename.")
    renamed = BrowserProfile.model_validate(browser.profile.model_dump() | {"name": name})
    with FileLock(str(config_dir() / "browsers.lock")):
        preferences = read_preferences()
        write_preferences(
            preferences.model_copy(
                update={
                    "profiles": tuple(
                        renamed if item.id == renamed.id else item for item in preferences.profiles
                    )
                }
            )
        )


def profile_lock(browser: BrowserChoice) -> FileLock:
    if browser.profile is None:
        raise BrowserSetupError("Choose a saved profile first.")
    root = validate_root(browser, local_path(browser, browser.profile.root))
    return FileLock(str(root.parent / f".tum-mcp-{root.name}.lock"), timeout=0)


def remove_profile(browser: BrowserChoice) -> None:
    profile = browser.profile
    if profile is None:
        raise BrowserSetupError("Choose a saved profile to remove.")
    with profile_lock(browser), FileLock(str(config_dir() / "browsers.lock")):
        remove_profile_data(browser)
        preferences = read_preferences()
        write_preferences(
            preferences.model_copy(
                update={
                    "profiles": tuple(
                        item for item in preferences.profiles if item.id != profile.id
                    ),
                    "last_profile": None
                    if preferences.last_profile == profile.id
                    else preferences.last_profile,
                    "last_browser": None
                    if preferences.last_profile == profile.id
                    else preferences.last_browser,
                }
            )
        )


def remove_profile_data(browser: BrowserChoice) -> None:
    profile = browser.profile
    if profile is None:
        raise BrowserSetupError("Choose a saved profile to remove.")
    source = local_path(browser, profile.root)
    root = validate_root(browser, source)
    if profile.managed and root.exists():
        expected = managed_root(browser).resolve() / profile.id
        if root != expected or source.is_symlink():
            raise BrowserSetupError("Profile ownership changed; browser data was preserved.")
        shutil.rmtree(root)
    cookie_file(profile).unlink(missing_ok=True)
