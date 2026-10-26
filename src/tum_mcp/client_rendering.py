"""Render the established host adapters into disposable profiles before activation."""

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from pydantic import JsonValue

from tum_mcp import __version__
from tum_mcp.client_config import Marketplace, client_config_path, read_client_config
from tum_mcp.client_hosts import ClientHost, StdioLaunch, client_launch, storage_environment
from tum_mcp.client_installs import MANAGED_ROOTS
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.skills import export_pack, implicit_invocation


def same_tree(left: Path, right: Path) -> bool:
    expected = {p.relative_to(left): p.read_bytes() for p in left.rglob("*") if p.is_file()}
    actual = {p.relative_to(right): p.read_bytes() for p in right.rglob("*") if p.is_file()}
    return expected == actual


def rendered_client(
    name: str, launch: StdioLaunch, host: ClientHost, *, include_studocu: bool | None = None
) -> tuple[dict[str, bytes], dict[str, JsonValue], dict[str, JsonValue] | None, str]:
    """Reuse the existing adapters in a disposable profile before touching real files."""
    if name not in MANAGED_ROOTS:
        return {}, dict(launch.entry()), None, "Reload your client's MCP servers after setup."
    with tempfile.TemporaryDirectory(prefix="tum-mcp-render-") as temporary:
        root = Path(temporary)
        staged = root / "staged"
        staged.mkdir()
        skills = staged / "skills"
        export_pack(skills, include_studocu=include_studocu)
        if name in {"cursor", "antigravity"}:
            content = {
                f"{MANAGED_ROOTS[name]}/{path.relative_to(skills).as_posix()}": path.read_bytes()
                for path in skills.rglob("*")
                if path.is_file()
            }
            return (
                content,
                dict(launch.entry()),
                None,
                f"{len(tuple(skills.iterdir()))} skills installed. "
                "Restart your client to reload skills and MCP tools.",
            )
        profile = root / "profile"
        messages = io.StringIO()
        with redirect_stdout(messages):
            if name == "codex":
                install_codex(
                    staged, profile, launch=launch if host == ClientHost.WINDOWS else None
                )
            else:
                install_claude(staged, profile, launch=launch)
        target = client_config_path(name, profile)
        server = read_client_config(target).mcpServers["tum"]
        if not isinstance(server, dict):
            raise CampusError(Code.INVALID_RESPONSE, "Generated MCP entry is invalid.")
        prefix = ".codex/plugins/local/tum-mcp" if name == "codex" else ".claude/skills"
        content = {
            path.relative_to(profile).as_posix(): path.read_bytes()
            for path in (profile / prefix).rglob("*")
            if path.is_file() and path != target
        }
        catalog = None
        if name == "codex":
            market = Marketplace.model_validate_json(
                (profile / ".agents/plugins/marketplace.json").read_bytes()
            )
            catalog = market.plugins[0]
        return content, server, catalog, messages.getvalue().strip()


def install_codex(staged: Path, home: Path, *, launch: StdioLaunch | None = None) -> None:
    for skill in (staged / "skills").iterdir():
        if (home / ".agents/skills" / skill.name).exists():
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Duplicate global campus skill; resolve it locally first."
            )
    manifest = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "tum-mcp",
        "version": __version__,
        "description": "Local TUM campus tools and workflows.",
        "extensions": {
            "com.openai": {
                "interface": {
                    "displayName": "TUM MCP",
                    "shortDescription": "TUM courses and assignments",
                    "category": "Education",
                    "capabilities": ["Read", "Edit"],
                }
            }
        },
    }
    (staged / "plugin.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if launch is None:
        scripts = staged / "scripts"
        scripts.mkdir()
        # Portable Agent Plugins reject absolute stdio executable paths. Node is the
        # npm consumer prerequisite; this contained launcher pins the managed Python.
        (scripts / "serve.mjs").write_text(
            "import { spawn } from 'node:child_process';\n"
            "const env = { ...process.env }; delete env.PYTHONPATH; delete env.PYTHONHOME;\n"
            f"Object.assign(env, {json.dumps(dict(storage_environment()))});\n"
            f"const backend = spawn({json.dumps(sys.executable)}, "
            "['-I', '-m', 'tum_mcp', 'serve'], { env, stdio: 'inherit', shell: false });\n"
            "for (const signal of ['SIGINT', 'SIGTERM']) "
            "process.on(signal, () => backend.kill(signal));\n"
            "backend.on('error', () => { "
            "console.error('TUM backend could not start; rerun setup.'); "
            "process.exitCode = 2; });\n"
            "backend.on('exit', code => { process.exitCode = code ?? 1; });\n",
            encoding="utf-8",
        )
    server = (
        launch.entry(typed=True)
        if launch
        else {"type": "stdio", "command": "node", "args": ["${PLUGIN_ROOT}/scripts/serve.mjs"]}
    )
    (staged / "mcp.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {"tum": server},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    destination = home / ".codex/plugins/local/tum-mcp"
    if destination.exists() and not same_tree(staged, destination):
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Installed plugin differs; export and review the new pack before replacing it.",
        )
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged, destination)
    catalog = home / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        json.loads(catalog.read_text(encoding="utf-8"))
        if catalog.exists()
        else {
            "name": "personal-local",
            "plugins": [],
        }
    )
    entry = {
        "name": "tum-mcp",
        "source": {"source": "local", "path": "./" + destination.relative_to(home).as_posix()},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Education",
    }
    existing["plugins"] = [p for p in existing["plugins"] if p["name"] != "tum-mcp"] + [entry]
    private_write(catalog, json.dumps(existing, indent=2).encode())
    print("Install/enable TUM MCP from your personal source in Codex Plugins and restart.")
    print("Disable the legacy TUM Moodle plugin when switching, to avoid duplicate tools/skills.")
    print("Client activation and skill routing still need a live verification.")


def install_claude(staged: Path, home: Path, *, launch: StdioLaunch | None = None) -> None:
    skills = home / ".claude/skills"
    target = home / ".claude.json"
    existing = read_client_config(target, for_update=True).model_dump()
    server = (launch or client_launch(ClientHost.LOCAL)).entry(typed=True)
    registered = existing.get("mcpServers", {}).get("tum")
    if registered is not None and registered != server:
        raise CampusError(Code.WORKSPACE_CONFLICT, "A different Claude MCP entry already uses tum.")
    for source in (staged / "skills").iterdir():
        if not implicit_invocation(source):
            entry = source / "SKILL.md"
            entry.write_text(
                entry.read_text(encoding="utf-8").replace(
                    "---\n", "---\ndisable-model-invocation: true\n", 1
                ),
                encoding="utf-8",
            )
        destination = skills / source.name
        if destination.exists() and not same_tree(source, destination):
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "A customized Claude skill already exists; review the diff locally.",
            )
    skills.mkdir(parents=True, exist_ok=True)
    for source in (staged / "skills").iterdir():
        if not (skills / source.name).exists():
            shutil.copytree(source, skills / source.name)
    existing.setdefault("mcpServers", {})["tum"] = server
    private_write(target, json.dumps(existing, indent=2).encode())
    print("Claude configuration written. Restart; verify the study workflows and MCP tools.")
