"""Remove only unchanged managed client files; retain all user campus data."""

import json
from pathlib import Path
from typing import Literal, assert_never

from tum_mcp.client_hosts import ClientHost, client_home, client_launch
from tum_mcp.clients import client_config_path, read_client_config, same_tree
from tum_mcp.errors import CampusError, Code
from tum_mcp.skills import bundled, export_pack
from tum_moodle.config import private_write


def uninstall_client(
    name: Literal["codex", "claude", "cursor", "antigravity", "generic"],
    home: Path | None = None,
    *,
    host: ClientHost = ClientHost.LOCAL,
) -> None:
    base = client_home(host, home)
    launch = client_launch(host)
    expected = launch.entry(typed=True)
    match name:
        case "cursor" | "antigravity":
            path = client_config_path(name, base)
            if path.exists():
                current = read_client_config(path, for_update=True)
                registered = current.mcpServers.get("tum")
                wanted = launch.entry()
                if registered is not None and registered != wanted:
                    raise CampusError(
                        Code.WORKSPACE_CONFLICT, "Customized MCP configuration was preserved."
                    )
                current.mcpServers.pop("tum", None)
                private_write(path, current.model_dump_json(indent=2).encode())
        case "generic":
            path = client_config_path(name, base, host=host)
            if path.exists():
                value = read_client_config(path, for_update=True).model_dump()
                expected_generic = launch.entry()
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
            value = read_client_config(target, for_update=True).model_dump()
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
