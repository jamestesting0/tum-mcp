"""Cache successful client probes without persisting configuration or credentials."""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, ValidationError

from tum_mcp import __version__
from tum_mcp.clients import hook_config
from tum_mcp.clients.config import client_config_path
from tum_mcp.clients.installs import Installation, receipt_path
from tum_mcp.commands.ui import State
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen

MAX_AGE: Final = 24 * 60 * 60


class Result(Frozen):
    fingerprint: str
    checked_at: float = Field(allow_inf_nan=False)
    state: Literal[State.READY, State.CONFIGURED]
    detail: str


def path_for(receipt: Installation) -> Path:
    return receipt_path(receipt.client, receipt.host, receipt.home).with_suffix(
        ".verification.json"
    )


def fingerprint(receipt: Installation) -> str:
    home, name = receipt.home, receipt.client
    digest = hashlib.sha256(receipt.model_dump_json().encode())
    digest.update(__version__.encode())
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper().startswith(
            ("TUM_", "CODEX_", "CLAUDE_", "CURSOR_", "GEMINI_", "ANTIGRAVITY_", "PYTHON")
        )
        or key.upper()
        in {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"}
    }
    digest.update(json.dumps(environment, sort_keys=True).encode())
    paths = {client_config_path(name, home, host=receipt.host), home / hook_config.PATHS[name]}
    if name == "codex":
        paths.update({home / ".codex/config.toml", home / ".agents/plugins/marketplace.json"})
        paths.update((home / ".codex/config.d").glob("*.toml"))
    if name == "cursor":
        paths.add(home / ".cursor/cli-config.json")
    for path in sorted(paths):
        digest.update(str(path).encode())
        digest.update(path.read_bytes() if path.is_file() else b"missing")
    executables = {sys.executable, str(receipt.server["command"])}
    native = {"codex": "codex", "claude": "claude", "cursor": "cursor-agent"}.get(name)
    if native:
        executables.add(native)
    for command in sorted(executables):
        resolved = shutil.which(command)
        digest.update(str((command, resolved)).encode())
        if resolved:
            target = Path(resolved).resolve()
            for path in (
                target,
                target.parent / "package.json",
                target.parent.parent / "package.json",
            ):
                if path.is_file():
                    stat = path.stat()
                    digest.update(
                        str((path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)).encode()
                    )
    return digest.hexdigest()


def load(path: Path, identity: str) -> tuple[State, str] | None:
    try:
        result = Result.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        return None
    age = time.time() - result.checked_at
    if result.fingerprint != identity or not 0 <= age < MAX_AGE:
        return None
    return (
        result.state,
        result.detail + f" Cached client check ({int(age // 3600)}h ago; valid for 24h).",
    )


def save(path: Path, identity: str, state: State, detail: str) -> None:
    if state in {State.READY, State.CONFIGURED}:
        result = Result(fingerprint=identity, checked_at=time.time(), state=state, detail=detail)
        private_write(path, result.model_dump_json().encode())
