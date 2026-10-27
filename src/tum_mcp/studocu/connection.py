"""Open the user's own browser without reading or copying Studocu credentials."""

import shutil
import subprocess
import webbrowser

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import is_wsl

URL = "https://www.studocu.com/"


def open_browser() -> None:
    if is_wsl():
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if shell:
            try:
                result = subprocess.run(  # noqa: S603 - fixed public URL and discovered OS executable
                    [shell, "-NoProfile", "-NonInteractive", "-Command", "Start-Process", URL],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
                if result.returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError):
                raise CampusError(
                    Code.ACTION_REQUIRED,
                    "Open https://www.studocu.com/ in your own browser and sign in.",
                ) from None
    try:
        if webbrowser.open_new_tab(URL):
            return
    except (OSError, webbrowser.Error):
        raise CampusError(
            Code.ACTION_REQUIRED, "Open https://www.studocu.com/ in your own browser and sign in."
        ) from None
    raise CampusError(
        Code.ACTION_REQUIRED, "Open https://www.studocu.com/ in your own browser and sign in."
    )
