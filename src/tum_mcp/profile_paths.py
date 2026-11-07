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


def protect_directory(browser: BrowserChoice, path: Path) -> None:
    if browser.windows_host:
        if path.is_symlink():
            raise BrowserSetupError("Saved browser directory cannot be a symbolic link.")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        _secure_windows_path(Path(launch_path(browser, path)))
    else:
        secure_directory(path)


def everyday_roots(browser: BrowserChoice) -> tuple[Path, ...]:
    """Exclude normal browser data, including other brands and preview channels."""
    if browser.windows_host or sys.platform == "win32":
        if browser.windows_host:
            host = windows_host()
            local = Path(wsl_path(str(host.local_data)))
            roaming = Path(wsl_path(str(host.home / "AppData/Roaming")))
        else:
            local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        roots = [
            local / suffix
            for suffix in (
                "Google/Chrome/User Data",
                "Google/Chrome Beta/User Data",
                "Google/Chrome Dev/User Data",
                "Google/Chrome SxS/User Data",
                "Microsoft/Edge/User Data",
                "Microsoft/Edge Beta/User Data",
                "Microsoft/Edge Dev/User Data",
                "Microsoft/Edge SxS/User Data",
                "BraveSoftware/Brave-Browser/User Data",
                "Chromium/User Data",
                "Vivaldi/User Data",
            )
        ]
        roots.extend(
            roaming / "Opera Software" / name for name in ("Opera Stable", "Opera GX Stable")
        )
        return tuple(roots)
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
        names = (
            "Google/Chrome",
            "Google/Chrome Beta",
            "Google/Chrome Dev",
            "Google/Chrome Canary",
            "Microsoft Edge",
            "Microsoft Edge Beta",
            "Microsoft Edge Dev",
            "Microsoft Edge Canary",
            "BraveSoftware/Brave-Browser",
            "Chromium",
            "Vivaldi",
            "com.operasoftware.Opera",
            "com.operasoftware.OperaGX",
        )
    else:
        base = Path(
            os.environ.get("CHROME_CONFIG_HOME")
            or os.environ.get("XDG_CONFIG_HOME")
            or Path.home() / ".config"
        )
        names = (
            "google-chrome",
            "google-chrome-beta",
            "google-chrome-unstable",
            "google-chrome-canary",
            "microsoft-edge",
            "microsoft-edge-beta",
            "microsoft-edge-dev",
            "BraveSoftware/Brave-Browser",
            "chromium",
            "vivaldi",
            "opera",
            "opera-gx",
        )
    roots = tuple(base / name for name in names)
    override = os.environ.get("CHROME_USER_DATA_DIR")
    return (*roots, Path(override).expanduser()) if override else roots


def validate_root(browser: BrowserChoice, path: Path) -> Path:
    root = path.resolve()
    if any(
        root.is_relative_to(item.resolve()) or item.resolve().is_relative_to(root)
        for item in everyday_roots(browser)
    ):
        raise BrowserSetupError(
            "Everyday browser profiles cannot be used. Choose a dedicated profile."
        )
    return root
