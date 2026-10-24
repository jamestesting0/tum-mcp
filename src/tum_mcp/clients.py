"""Explicit, conflict-safe client registration. Never runs during package install."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from tum_mcp import __version__
from tum_mcp.client_hosts import ClientHost, StdioLaunch, client_home, client_launch
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import config_dir
from tum_mcp.skills import export_pack, inspect_skills
from tum_moodle.config import private_write

CLIENTS = ("codex", "claude", "cursor", "antigravity", "generic")


class ClientConfiguration(BaseModel):
    model_config = ConfigDict(extra="allow")
    mcpServers: dict[str, JsonValue] = Field(default_factory=dict)


def client_config_path(name: str, home: Path, *, host: ClientHost = ClientHost.LOCAL) -> Path:
    match name:
        case "cursor":
            return home / ".cursor/mcp.json"
        case "antigravity":
            current = home / ".gemini/config/mcp_config.json"
            legacy = home / ".gemini/antigravity/mcp_config.json"
            return legacy if legacy.is_file() and not current.exists() else current
        case "claude":
            return home / ".claude.json"
        case "generic":
            return (
                home / ".config/tum-mcp/mcp-wsl.json"
                if host == ClientHost.WINDOWS
                else config_dir() / "mcp.json"
            )
        case "codex":
            return home / ".codex/plugins/local/tum-mcp/mcp.json"
        case _:
            raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Choose a supported MCP client.")


def read_client_config(path: Path, *, for_update: bool = False) -> ClientConfiguration:
    if for_update and path.is_symlink():
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Client configuration is a symbolic link; update its target manually.",
        )
    if not path.exists():
        return ClientConfiguration()
    try:
        return ClientConfiguration.model_validate_json(path.read_bytes())
    except (ValidationError, OSError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Client configuration is invalid; preserve and repair it locally.",
        ) from None


def install_stdio_client(name: str, home: Path, launch: StdioLaunch) -> None:
    target = client_config_path(name, home)
    current = read_client_config(target, for_update=True)
    server = launch.entry()
    existing = current.mcpServers.get("tum")
    if existing is not None and existing != server:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "A customized MCP entry already uses tum; preserve it."
        )
    current.mcpServers["tum"] = server
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_write(target, current.model_dump_json(indent=2).encode())
    print(f"{name.title()} MCP configuration saved. Reload its MCP servers to activate TUM MCP.")
    print("Host activation is not verified. Use skills export for portable workflow skills.")


def same_tree(left: Path, right: Path) -> bool:
    expected = {p.relative_to(left): p.read_bytes() for p in left.rglob("*") if p.is_file()}
    actual = {p.relative_to(right): p.read_bytes() for p in right.rglob("*") if p.is_file()}
    return expected == actual


def install_client(
    name: str, home: Path | None = None, *, host: ClientHost = ClientHost.LOCAL
) -> None:
    base = client_home(host, home)
    launch = client_launch(host)
    if name not in CLIENTS:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Choose codex, claude, cursor, antigravity, or generic."
        )
    with FileLock(str(config_dir() / "client-install.lock")):
        if name in {"cursor", "antigravity"}:
            install_stdio_client(name, base, launch)
            return
        if name == "generic":
            target = client_config_path(name, base, host=host)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            current = read_client_config(target, for_update=True).model_dump()
            server = launch.entry()
            registered = current.get("mcpServers", {}).get("tum")
            if registered is not None and registered != server:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "A customized generic entry already uses tum."
                )
            current.setdefault("mcpServers", {})["tum"] = server
            private_write(target, json.dumps(current, indent=2).encode())
            return
        with tempfile.TemporaryDirectory(prefix="tum-mcp-client-") as temporary:
            staged = Path(temporary) / "tum-mcp"
            staged.mkdir()
            export_pack(staged / "skills")
            if name == "codex":
                install_codex(staged, base, launch=launch if host == ClientHost.WINDOWS else None)
            else:
                install_claude(staged, base, launch=launch)


def install_codex(staged: Path, home: Path, *, launch: StdioLaunch | None = None) -> None:
    for info in inspect_skills():
        if (home / ".agents/skills" / info["name"]).exists():
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
    submission = staged / "skills/tum-artemis-submit/SKILL.md"
    content = submission.read_text(encoding="utf-8")
    submission.write_text(
        content.replace("---\n", "---\ndisable-model-invocation: true\n", 1), encoding="utf-8"
    )
    # Claude uses its frontmatter control rather than Codex's agents/openai.yaml.
    for source in (staged / "skills").iterdir():
        metadata_path = source / "agents/openai.yaml"
        if metadata_path.exists():
            parsed = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
            if parsed.get("policy", {}).get("allow_implicit_invocation") is not False:
                raise CampusError(
                    Code.INVALID_RESPONSE, "Submission invocation policy is inconsistent."
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
    print("Claude configuration written. Restart; verify /tum-artemis-prepare and MCP tools.")
