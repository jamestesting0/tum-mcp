"""Remove only unchanged managed client files; retain all user campus data."""

import json
import sys
from pathlib import Path
from typing import Literal, assert_never

from tum_mcp.clients import same_tree
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import config_dir
from tum_mcp.skills import bundled, export_pack
from tum_moodle.config import private_write


def uninstall_client(name: Literal["codex", "claude", "generic"], home: Path | None = None) -> None:
    base = home or Path.home()
    expected = {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-I", "-m", "tum_mcp", "serve"],
    }
    match name:
        case "generic":
            path = config_dir() / "mcp.json"
            if path.exists():
                value = json.loads(path.read_text(encoding="utf-8"))
                expected_generic = {
                    "command": sys.executable,
                    "args": ["-I", "-m", "tum_mcp", "serve"],
                }
                entry = value.get("mcpServers", {}).get("tum")
                if entry is not None and entry != expected_generic:
                    raise CampusError(
                        Code.WORKSPACE_CONFLICT,
                        "Generic configuration was customized; preserve it.",
                    )
                value.get("mcpServers", {}).pop("tum", None)
                if value.get("mcpServers") or set(value) - {"mcpServers"}:
                    private_write(path, json.dumps(value, indent=2).encode())
                else:
                    path.unlink()
        case "claude":
            target = base / ".claude.json"
            value = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            entry = value.get("mcpServers", {}).get("tum")
            if entry is not None and entry != expected:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Claude MCP registration changed; preserve it."
                )
            # Validate every managed skill before removing any file.
            from tempfile import TemporaryDirectory

            with TemporaryDirectory(prefix="tum-mcp-uninstall-") as temporary:
                staged = Path(temporary)
                source = staged / "skills"
                export_pack(source)
                submission = source / "tum-artemis-submit/SKILL.md"
                submission.write_text(
                    submission.read_text(encoding="utf-8").replace(
                        "---\n", "---\ndisable-model-invocation: true\n", 1
                    ),
                    encoding="utf-8",
                )
                for skill in bundled().iterdir():
                    destination = base / ".claude/skills" / skill.name
                    if destination.exists() and not same_tree(source / skill.name, destination):
                        raise CampusError(
                            Code.WORKSPACE_CONFLICT,
                            "Customized Claude skill preserved; export/review it locally.",
                        )
                for skill in bundled().iterdir():
                    destination = base / ".claude/skills" / skill.name
                    if destination.is_dir():
                        for file in sorted(destination.rglob("*"), reverse=True):
                            file.unlink() if file.is_file() else file.rmdir()
                        destination.rmdir()
            value.get("mcpServers", {}).pop("tum", None)
            if target.exists():
                private_write(target, json.dumps(value, indent=2).encode())
        case "codex":
            # Cached/active plugin state belongs to Codex; let its supported UI own removal.
            print(
                "Remove TUM MCP in Codex Plugins, then restart. Local source is kept for rollback."
            )
        case unreachable:
            assert_never(unreachable)
    print("Campus credentials, settings, runtimes, downloads, and workspaces were preserved.")
