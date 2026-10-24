"""Local client registration and Windows clients backed by the same WSL runtime."""

import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, assert_never

from tum_mcp.settings import config_path, data_path
from tum_moodle.browsers import BrowserSetupError, is_wsl, windows_host, wsl_path
from tum_moodle.downloads import downloads_root
from tum_moodle.platforms import data_root


class ClientHost(StrEnum):
    LOCAL = "local"
    WINDOWS = "windows"


class StdioEntry(TypedDict):
    command: str
    args: list[str]
    type: NotRequired[Literal["stdio"]]
    env: NotRequired[dict[str, str]]


@dataclass(frozen=True, slots=True)
class StdioLaunch:
    command: str
    arguments: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = ()

    def entry(self, *, typed: bool = False) -> StdioEntry:
        result: StdioEntry = {"command": self.command, "args": list(self.arguments)}
        if self.environment:
            result["env"] = dict(self.environment)
        if typed:
            result["type"] = "stdio"
        return result


def client_home(host: ClientHost, home: Path | None = None) -> Path:
    match host:
        case ClientHost.LOCAL:
            return home or Path.home()
        case ClientHost.WINDOWS:
            if not is_wsl():
                raise BrowserSetupError(
                    "--host windows is for WSL. On native Windows, use the default local host."
                )
            return home or Path(wsl_path(str(windows_host().home)))
        case unreachable:
            assert_never(unreachable)


def storage_environment() -> tuple[tuple[str, str], ...]:
    return (
        ("TUM_MCP_DATA_DIR", str(data_path())),
        ("TUM_MCP_CONFIG_DIR", str(config_path())),
        ("TUM_MOODLE_DATA_DIR", str(data_root().expanduser().resolve())),
        ("TUM_MOODLE_DOWNLOAD_DIR", str(downloads_root().expanduser().resolve())),
    )


def client_launch(host: ClientHost) -> StdioLaunch:
    match host:
        case ClientHost.LOCAL:
            return StdioLaunch(
                sys.executable, ("-I", "-m", "tum_mcp", "serve"), storage_environment()
            )
        case ClientHost.WINDOWS:
            if not is_wsl():
                raise BrowserSetupError("Windows client registration must be run from WSL.")
            import pwd

            distribution = os.environ.get("WSL_DISTRO_NAME", "")
            if not distribution or "\n" in distribution or "\x00" in distribution:
                raise BrowserSetupError(
                    "WSL_DISTRO_NAME is missing. Run setup inside your WSL distribution."
                )
            user = pwd.getpwuid(os.getuid()).pw_name
            variables = tuple(f"{name}={value}" for name, value in storage_environment())
            return StdioLaunch(
                "wsl.exe",
                (
                    "--distribution",
                    distribution,
                    "--user",
                    user,
                    "--exec",
                    "/usr/bin/env",
                    *variables,
                    sys.executable,
                    "-I",
                    "-m",
                    "tum_mcp",
                    "serve",
                ),
            )
        case unreachable:
            assert_never(unreachable)
