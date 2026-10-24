"""Explicit, conflict-safe client registration. Never runs during package install."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml
from filelock import FileLock

from tum_mcp import __version__
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import config_dir
from tum_mcp.skills import export_pack, inspect_skills
from tum_moodle.config import private_write


def same_tree(left: Path, right: Path) -> bool:
    expected = {p.relative_to(left): p.read_bytes() for p in left.rglob("*") if p.is_file()}
    actual = {p.relative_to(right): p.read_bytes() for p in right.rglob("*") if p.is_file()}
    return expected == actual


def install_client(name: str, home: Path | None = None) -> None:
    base = home or Path.home()
    if name not in {"codex", "claude", "generic"}:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Choose codex, claude, or generic.")
    with FileLock(str(config_dir() / "client-install.lock")):
        if name == "generic":
            target = config_dir() / "mcp.json"
            current = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            server = {"command": sys.executable, "args": ["-I", "-m", "tum_mcp", "serve"]}
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
                install_codex(staged, base)
            else:
                install_claude(staged, base)


def install_codex(staged: Path, home: Path) -> None:
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
        "backend.on('error', () => { console.error('TUM backend could not start; rerun setup.'); "
        "process.exitCode = 2; });\n"
        "backend.on('exit', code => { process.exitCode = code ?? 1; });\n",
        encoding="utf-8",
    )
    (staged / "mcp.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {
                    "tum": {
                        "type": "stdio",
                        "command": "node",
                        "args": ["${PLUGIN_ROOT}/scripts/serve.mjs"],
                    }
                },
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


def install_claude(staged: Path, home: Path) -> None:
    skills = home / ".claude/skills"
    target = home / ".claude.json"
    existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    server = {"type": "stdio", "command": sys.executable, "args": ["-I", "-m", "tum_mcp", "serve"]}
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
