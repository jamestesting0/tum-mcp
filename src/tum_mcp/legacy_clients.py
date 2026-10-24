"""Adopt old client files only when they match a retained runtime's canonical export."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.client_hosts import ClientHost
from tum_mcp.client_installs import ClientName, Installation, read_owned_file
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import data_path


def managed_python(value: str) -> Path | None:
    original = Path(value)
    path = original.parent.resolve() / original.name
    runtimes = data_path() / "runtimes"
    suffix = Path("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        relative = path.relative_to(runtimes)
        if len(relative.parts) not in {3, 4} or Path(*relative.parts[-2:]) != suffix:
            return None
        identity = relative.parts[0]
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            return None
        if len(relative.parts) == 4 and not re.fullmatch(r"env-[A-Za-z0-9]+", relative.parts[1]):
            return None
        runtime = path.parent.parent
        if runtime.resolve() != runtime or not path.is_file():
            return None
        marker = runtime / ".tum-mcp-ready"
        if marker.is_symlink() or marker.read_text() != identity:
            return None
    except (OSError, ValueError):
        return None
    return original


def legacy_installation(
    name: ClientName,
    host: ClientHost,
    home: Path,
    entry: JsonValue,
    desired: dict[str, JsonValue],
) -> Installation | None:
    if not isinstance(entry, dict):
        return None
    candidate = entry.get("command")
    windows = host == ClientHost.WINDOWS
    if windows:
        arguments = entry.get("args")
        if not isinstance(arguments, list) or len(arguments) < 5:
            return None
        candidate = arguments[-5]
    elif name == "codex":
        if entry != desired:
            return None
        wrapper = read_owned_file(home / ".codex/plugins/local/tum-mcp/scripts/serve.mjs", home)
        if wrapper is None:
            return None
        match = re.search(rb'const backend = spawn\(("(?:[^"\\]|\\.)*"),', wrapper)
        if match is None:
            return None
        try:
            candidate = json.loads(match[1])
        except (json.JSONDecodeError, UnicodeError):
            return None
    if not isinstance(candidate, str) or (python := managed_python(candidate)) is None:
        return None
    if name != "codex" or windows:
        canonical = json.loads(json.dumps(desired))
        if windows:
            canonical["args"][-5] = str(python)
        else:
            canonical["command"] = str(python)
        # Old releases did not pin native desktop storage variables. No other
        # additional/edited environment is adopted without an ownership receipt.
        without_environment = {key: value for key, value in canonical.items() if key != "env"}
        legacy_windows = dict(without_environment)
        if windows:
            legacy_windows["args"] = [
                value
                for value in canonical["args"]
                if not isinstance(value, str) or not value.startswith("TUM_MOODLE_DOWNLOAD_DIR=")
            ]
        if entry != canonical and entry != without_environment and entry != legacy_windows:
            return None
    content: dict[str, str] = {}
    catalog = None
    if name in {"codex", "claude"}:
        with tempfile.TemporaryDirectory(prefix="tum-mcp-legacy-") as temporary:
            root = Path(temporary)
            profile = root / "profile"
            env = dict(os.environ)
            env.update(TUM_MCP_DATA_DIR=str(root / "data"), TUM_MCP_CONFIG_DIR=str(root / "config"))
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            script = (
                "from pathlib import Path; import sys; "
                "from tum_mcp.clients import install_client; "
                "install_client(sys.argv[1], Path(sys.argv[2]))"
            )
            try:
                result = subprocess.run(  # noqa: S603
                    [str(python), "-I", "-c", script, name, str(profile)],
                    env=env,
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    "Previous client export could not be verified; preserved.",
                ) from None
            if result.returncode != 0:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Previous client export failed; preserved."
                )
            prefix = ".codex/plugins/local/tum-mcp" if name == "codex" else ".claude/skills"
            for path in (profile / prefix).rglob("*"):
                if path.is_file():
                    relative = path.relative_to(profile).as_posix()
                    if name == "codex" and (
                        path.name == "mcp.json" or windows and "scripts" in path.parts
                    ):
                        continue
                    content[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            if name == "codex":
                market = json.loads((profile / ".agents/plugins/marketplace.json").read_bytes())
                catalog = market["plugins"][0]
    return Installation(
        client=name,
        host=host,
        home=home,
        version="legacy",
        server=entry,
        files=content,
        catalog=catalog,
    )
