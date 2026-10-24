"""Installed Chromium browsers and Windows-host paths, without opening user profiles."""

import base64
import binascii
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PureWindowsPath
from typing import Final


class BrowserSetupError(RuntimeError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"SETUP_REQUIRED: {message}")


@dataclass(frozen=True, slots=True)
class BrowserChoice:
    name: str
    executable: str
    windows_host: bool = False

    @property
    def label(self) -> str:
        return self.name + (" (Windows)" if self.windows_host else "")


@dataclass(frozen=True, slots=True)
class WindowsHost:
    home: PureWindowsPath
    local_data: PureWindowsPath
    program_files: tuple[PureWindowsPath, ...]
    architecture: str


def is_wsl() -> bool:
    return sys.platform == "linux" and (
        bool(os.environ.get("WSL_DISTRO_NAME"))
        or "microsoft" in platform.release().lower()
        or "wsl" in platform.release().lower()
    )


def wsl_path(path: str, *, windows: bool = False) -> str:
    executable = shutil.which("wslpath")
    if executable is None:
        raise BrowserSetupError("WSL path translation requires wslpath.")
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "-w" if windows else "-u", path],
            capture_output=True,
            check=True,
            timeout=10,
            encoding="utf-8",
        )
        value = result.stdout.strip()
        if not value or len(value) > 32768 or "\n" in value:
            raise BrowserSetupError("WSL could not translate a required browser path.")
        return value
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise BrowserSetupError(
            "WSL path translation failed. Check that wslpath is available."
        ) from None


@lru_cache(maxsize=1)
def windows_host() -> WindowsHost:
    """Ask Windows for its own paths; no assumptions about drive letters or /mnt/c."""
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not shell:
        raise BrowserSetupError(
            "Windows interop is unavailable. Enable WSL interop and Windows PATH, then restart WSL."
        )
    script = (
        "$ErrorActionPreference='Stop'; "
        "$items=@([Environment]::GetFolderPath('UserProfile'),"
        "[Environment]::GetFolderPath('LocalApplicationData'),"
        "[Environment]::GetFolderPath('ProgramFiles'),"
        "[Environment]::GetFolderPath('ProgramFilesX86'),"
        "[Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()); "
        "foreach($item in $items){[Console]::WriteLine("
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($item)))}"
    )
    try:
        result = subprocess.run(  # noqa: S603
            [shell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
            check=True,
        )
        values = tuple(
            base64.b64decode(line, validate=True).decode("utf-8")
            for line in result.stdout.splitlines()
        )
    except (OSError, subprocess.SubprocessError, UnicodeError, binascii.Error):
        raise BrowserSetupError(
            "Could not inspect Windows browser paths through WSL interop."
        ) from None
    if len(values) != 5 or not all(values[index] for index in (0, 1, 4)):
        raise BrowserSetupError("Windows returned incomplete browser setup information.")
    if any(value and not PureWindowsPath(value).is_absolute() for value in values[:4]):
        raise BrowserSetupError("Windows returned invalid absolute browser paths.")
    architecture = values[4].lower()
    if architecture not in {"x64", "arm64"}:
        raise BrowserSetupError("The Windows browser bridge requires x64 or ARM64 Windows.")
    return WindowsHost(
        home=PureWindowsPath(values[0]),
        local_data=PureWindowsPath(values[1]),
        program_files=tuple(PureWindowsPath(value) for value in values[2:4] if value),
        architecture=architecture,
    )


MAC_BROWSERS: Final = (
    ("Google Chrome", "Google Chrome.app/Contents/MacOS/Google Chrome"),
    ("Microsoft Edge", "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ("Brave", "Brave Browser.app/Contents/MacOS/Brave Browser"),
    ("Chromium", "Chromium.app/Contents/MacOS/Chromium"),
    ("Vivaldi", "Vivaldi.app/Contents/MacOS/Vivaldi"),
    ("Opera", "Opera.app/Contents/MacOS/Opera"),
    ("Opera GX", "Opera GX.app/Contents/MacOS/Opera GX"),
    ("Chrome Canary", "Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
    ("Edge Beta", "Microsoft Edge Beta.app/Contents/MacOS/Microsoft Edge Beta"),
)
LINUX_BROWSERS: Final = (
    ("Google Chrome", ("google-chrome", "google-chrome-stable")),
    ("Microsoft Edge", ("microsoft-edge", "microsoft-edge-stable")),
    ("Brave", ("brave-browser", "brave-browser-stable", "brave")),
    ("Chromium", ("chromium", "chromium-browser", "ungoogled-chromium")),
    ("Vivaldi", ("vivaldi", "vivaldi-stable")),
    ("Opera", ("opera",)),
    ("Chrome Beta", ("google-chrome-beta",)),
    ("Chrome Dev", ("google-chrome-unstable",)),
    ("Edge Beta", ("microsoft-edge-beta",)),
    ("Edge Dev", ("microsoft-edge-dev",)),
)
WINDOWS_BROWSERS: Final = (
    ("Microsoft Edge", "Microsoft/Edge/Application/msedge.exe"),
    ("Google Chrome", "Google/Chrome/Application/chrome.exe"),
    ("Brave", "BraveSoftware/Brave-Browser/Application/brave.exe"),
    ("Chromium", "Chromium/Application/chrome.exe"),
    ("Vivaldi", "Vivaldi/Application/vivaldi.exe"),
    ("Opera", "Programs/Opera/opera.exe"),
    ("Opera GX", "Programs/Opera GX/opera.exe"),
    ("Chrome Beta", "Google/Chrome Beta/Application/chrome.exe"),
    ("Chrome Canary", "Google/Chrome SxS/Application/chrome.exe"),
    ("Edge Beta", "Microsoft/Edge Beta/Application/msedge.exe"),
    ("Edge Dev", "Microsoft/Edge Dev/Application/msedge.exe"),
)


def _windows_candidates(root: Path, suffix: str) -> tuple[Path, ...]:
    path = root / suffix
    if "Opera" not in suffix:
        return (path,)
    # Opera keeps opera.exe inside a version directory on some installations.
    versions = sorted(path.parent.glob("[0-9]*.*/opera.exe"), reverse=True)
    return (path, *versions)


def discover_browsers() -> tuple[BrowserChoice, ...]:
    """Inspect executable locations only. An explicit custom binary takes precedence."""
    if custom := os.environ.get("TUM_MCP_BROWSER"):
        windows = is_wsl() and PureWindowsPath(custom).is_absolute()
        path = wsl_path(custom) if windows else shutil.which(custom) or custom
        candidate = Path(path).expanduser()
        if not candidate.is_file() or (not windows and not os.access(candidate, os.X_OK)):
            raise BrowserSetupError("TUM_MCP_BROWSER must point to an executable Chromium browser.")
        return (
            BrowserChoice(
                "Custom Chromium browser", custom if windows else str(candidate.resolve()), windows
            ),
        )
    found: list[BrowserChoice] = []
    match sys.platform:
        case "darwin":
            for name, suffix in MAC_BROWSERS:
                for root in (Path("/Applications"), Path.home() / "Applications"):
                    path = root / suffix
                    if path.is_file() and os.access(path, os.X_OK):
                        found.append(BrowserChoice(name, str(path.resolve())))
        case "win32":
            roots = [
                Path(value)
                for key in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
                if (value := os.environ.get(key))
            ]
            for name, suffix in WINDOWS_BROWSERS:
                for root in roots:
                    for path in _windows_candidates(root, suffix):
                        if path.is_file():
                            found.append(BrowserChoice(name, str(path)))
                            break
        case "linux":
            if is_wsl():
                host = windows_host()
                roots = tuple(
                    (root, Path(wsl_path(str(root))))
                    for root in (host.local_data, *host.program_files)
                )
                for name, suffix in WINDOWS_BROWSERS:
                    for root, linux_root in roots:
                        for path in _windows_candidates(linux_root, suffix):
                            if path.is_file():
                                executable = root / path.relative_to(linux_root).as_posix()
                                found.append(BrowserChoice(name, str(executable), True))
                                break
            if not is_wsl() or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                for name, commands in LINUX_BROWSERS:
                    for command in commands:
                        if path := shutil.which(command):
                            found.append(BrowserChoice(name, str(Path(path).resolve())))
        case _:
            raise BrowserSetupError("Browser sign-in supports macOS, Windows, Linux and WSL.")
    result: list[BrowserChoice] = []
    seen: set[str] = set()
    for browser in found:
        key = (
            browser.executable.casefold()
            if browser.windows_host or sys.platform == "win32"
            else browser.executable
        )
        if key not in seen:
            seen.add(key)
            result.append(browser)
    return tuple(result)
