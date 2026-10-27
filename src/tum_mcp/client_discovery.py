"""Bounded, read-only discovery of client installations, separate from MCP config."""

import os
import shutil
from pathlib import Path
from typing import Final, assert_never

from tum_mcp.client_hosts import ClientHost
from tum_mcp.client_installs import ClientName
from tum_mcp.moodle.platforms import System, system

MAC_APPLICATIONS: Final = Path("/Applications")
LINUX_APPLICATIONS: Final = (
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
)


def client_installed(name: ClientName, home: Path, host: ClientHost) -> bool:
    """Look for executable/app installation evidence without launching a client."""
    if name == "generic":
        return False
    windows = host == ClientHost.WINDOWS or system() == System.WINDOWS
    commands = (f"{name}.exe", f"{name}.cmd") if windows else (name,)
    if any(shutil.which(command) for command in commands):
        return True
    if windows:
        local = home / "AppData/Local"
        candidates = [
            home / ".local/bin" / f"{name}.exe",
            home / "AppData/Roaming/npm" / f"{name}.cmd",
            local / "Microsoft/WindowsApps" / f"{name}.exe",
        ]
        match name:
            case "cursor" | "antigravity":
                title = name.title()
                roots = [local / "Programs", home.parent.parent / "Program Files"]
                if host == ClientHost.LOCAL:
                    roots.extend(
                        Path(value)
                        for key in ("PROGRAMFILES", "PROGRAMFILES(X86)")
                        if (value := os.environ.get(key))
                    )
                candidates.extend(root / title / f"{title}.exe" for root in roots)
            case "codex" | "claude":
                pass
            case unreachable:
                assert_never(unreachable)
        return any(path.is_file() for path in candidates)
    match system():
        case System.MACOS:
            # Claude Code is a CLI; the unrelated Claude desktop app is not evidence.
            return name != "claude" and any(
                (root / f"{name.title()}.app").is_dir()
                for root in (MAC_APPLICATIONS, home / "Applications")
            )
        case System.LINUX:
            return any(
                (root / f"{name}.desktop").is_file()
                for root in (
                    home / ".local/share/applications",
                    *LINUX_APPLICATIONS,
                )
            )
        case System.WINDOWS:
            return False  # Handled above, including Windows clients discovered from WSL.
        case unreachable:
            assert_never(unreachable)
