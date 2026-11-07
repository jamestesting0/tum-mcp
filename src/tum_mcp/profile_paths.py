import hashlib
import os
import sys
from pathlib import Path, PureWindowsPath

from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError, windows_host, wsl_path
from tum_mcp.moodle.secret_files import _secure_windows_path, secure_directory
from tum_mcp.settings import data_path


def managed_root(browser: BrowserChoice) -> Path:
    identity = browser.executable
    if browser.windows_host or sys.platform == "win32":
        identity = str(PureWindowsPath(identity)).casefold()
    key = hashlib.sha256(identity.encode()).hexdigest()[:16]
    if browser.windows_host:
        scope = hashlib.sha256(
            (os.environ.get("WSL_DISTRO_NAME", "") + str(data_path())).encode()
        ).hexdigest()[:16]
        return (
            Path(wsl_path(str(windows_host().local_data / "TUMMCP/browser-profiles"))) / scope / key
        )
    return data_path() / "browser-profiles" / key


def local_path(browser: BrowserChoice, value: str) -> Path:
    if browser.windows_host and PureWindowsPath(value).is_absolute():
        return Path(wsl_path(value))
    return Path(value).expanduser().absolute()


def launch_path(browser: BrowserChoice, path: Path) -> str:
    return wsl_path(str(path), windows=True) if browser.windows_host else str(path)


def windows_driver_path(path: str) -> str:
    # Python must see an absolute POSIX path before the Windows driver receives it.
    value = PureWindowsPath(path).as_posix()
    if value.startswith("//"):
        return "//?/UNC/" + value.removeprefix("//")
    return "//?/" + value


def protect_directory(browser: BrowserChoice, path: Path) -> None:
    if browser.windows_host:
        if path.is_symlink():
            raise BrowserSetupError("Saved browser directory cannot be a symbolic link.")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        _secure_windows_path(Path(launch_path(browser, path)))
    else:
        secure_directory(path)


def profile_root(browser: BrowserChoice) -> Path:
    profile = browser.profile
    if profile is None:
        raise BrowserSetupError("Choose a saved profile first.")
    source = local_path(browser, profile.root)
    root = source.resolve()
    expected = managed_root(browser).resolve() / profile.id
    if source.is_symlink() or root != expected:
        raise BrowserSetupError("Profile ownership changed; browser data was preserved.")
    return root
