"""Git operations with sanitized URLs and a repository-scoped credential helper."""

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Account, config_dir, data_dir

CONFIG: Final = (
    "credential.helper=",
    "credential.useHttpPath=true",
    "core.hooksPath=" + os.devnull,
    "core.fsmonitor=false",
    "http.followRedirects=false",
    "http.sslVerify=true",
    "protocol.file.allow=never",
    "protocol.ext.allow=never",
    "submodule.recurse=false",
)

SAFE_LOCAL_CONFIG: Final = re.compile(
    r"core\.(repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|precomposeunicode)|"
    r"remote\.origin\.(url|fetch)|branch\.[A-Za-z0-9_./-]+\.(remote|merge)"
)


def repository_url(value: str, account: Account) -> str:
    parts = urlsplit(value)
    origin = urlsplit(account.origin)
    if (
        parts.scheme != "https"
        or parts.hostname != origin.hostname
        or parts.port not in {None, 443}
        or parts.query
        or parts.fragment
        or not parts.path.startswith("/git/")
        or "%" in parts.path
        or any(part in {".", "..", ""} for part in parts.path[1:].split("/"))
    ):
        raise CampusError(
            Code.SCOPE_DENIED, "Repository must be an exact HTTPS path on this instance."
        )
    return account.origin + parts.path


def run_git(directory: Path, arguments: list[str], account: Account | None = None) -> str:
    executable = shutil.which("git")
    if not executable:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Install Git before preparing a workspace.")
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TMP", "TEMP"}
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_SSH_COMMAND": "false",
        }
    )
    options = [piece for item in CONFIG for piece in ("-c", item)]
    if account:
        metadata = directory / ".git"
        if metadata.exists():
            if not metadata.is_dir() or metadata.is_symlink() or (metadata / "config").is_symlink():
                raise CampusError(Code.SCOPE_DENIED, "Git metadata must be local before access.")
            try:
                inspection = subprocess.run(  # noqa: S603
                    [
                        executable,
                        *options,
                        "-C",
                        str(directory),
                        "config",
                        "--local",
                        "--no-includes",
                        "--list",
                        "-z",
                    ],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                raise CampusError(
                    Code.SCOPE_DENIED, "Cannot inspect local Git configuration."
                ) from None
            if inspection.returncode or any(
                not SAFE_LOCAL_CONFIG.fullmatch(entry.split("\n", 1)[0])
                for entry in inspection.stdout.split("\0")
                if entry
            ):
                raise CampusError(
                    Code.SCOPE_DENIED,
                    "Unexpected local Git configuration; review it before credentialed access.",
                )
        environment.update(
            {
                "TUM_MCP_GIT_ACCOUNT": account.id,
                "TUM_MCP_CONFIG_DIR": str(config_dir()),
                "TUM_MCP_DATA_DIR": str(data_dir()),
            }
        )
        helper = f"!{shlex.quote(sys.executable)} -I -m tum_mcp.git_helper"
        options.extend(["-c", f"credential.helper={helper}"])
    try:
        result = subprocess.run(  # noqa: S603
            [executable, *options, "-C", str(directory), *arguments],
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CampusError(
            Code.OFFLINE, "Git failed or timed out; no automatic retry was made."
        ) from None
    if result.returncode:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Git operation failed; raw output omitted to protect credentials.",
        )
    return result.stdout if "-z" in arguments else result.stdout.strip()
