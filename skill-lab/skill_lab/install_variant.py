"""Install one variant's skills and guarded TUM server into a lab host profile.

Usage: <variant python> -I install_variant.py --host claude|codex --home DIR --proxy FILE
       --block a,b [--downloads DIR]
Runs on the variant's interpreter so the installed files come from the variant's own code.
Claude: `--home` is the profile's CLAUDE_CONFIG_DIR; `install_claude` (as `tum-mcp setup` uses
it) renders into a scratch HOME and its `.claude/` content moves into the config dir, because
macOS keeps Claude's login in the real user's keychain. Codex: `--home` is the profile HOME; the
skills and an MCP entry are written directly, because a plugin cannot put the tool filter in
front of the server.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

MARKER = ".skill-lab-install.json"
HOOK_MARKER = ".skill-lab-hooks.json"


def toml_string(value: str) -> str:
    return json.dumps(value)


def staged_skills(destination: Path) -> list[str]:
    from tum_mcp.skills import active_skill, bundled

    destination.mkdir(parents=True)
    names = []
    for source in sorted(bundled().iterdir()):
        if source.is_dir() and active_skill(source.name, None):
            shutil.copytree(source, destination / source.name)
            names.append(source.name)
    return names


def client_module(name: str):
    """Load the integration module from this variant, including historical flat packages."""
    legacy = f"tum_mcp.client_{name}"
    return import_module(legacy if find_spec(legacy) else f"tum_mcp.clients.{name}")


def launch(proxy: str, block: str):
    hosts = client_module("hosts")

    backend = (sys.executable, "-I", "-m", "tum_mcp", "serve")
    return hosts.StdioLaunch(
        sys.executable, ("-I", proxy, "--block", block, "--", *backend), hosts.storage_environment()
    )


def remove_previous(home: Path) -> None:
    owned_hooks = home / HOOK_MARKER
    if owned_hooks.is_file():
        from tum_mcp.clients.hook_config import writes

        for change in writes("codex", home, {}, json.loads(owned_hooks.read_text())):
            if change.after is None:
                change.path.unlink()
            else:
                change.path.write_bytes(change.after)
        owned_hooks.unlink()
    marker = home / MARKER
    if not marker.is_file():
        return
    previous = json.loads(marker.read_text(encoding="utf-8"))
    for relative in previous.get("paths", []):
        target = home / relative
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    config = home / ".claude.json"
    if config.is_file():
        data = json.loads(config.read_text(encoding="utf-8"))
        if data.get("mcpServers", {}).pop("tum", None) is not None:
            config.write_text(json.dumps(data, indent=2), encoding="utf-8")


def install_claude_profile(staged: Path, config: Path, entry_launch) -> list[str]:
    install_claude = client_module("rendering").install_claude

    with tempfile.TemporaryDirectory(prefix="skill-lab-claude-") as scratch:
        home = Path(scratch)
        install_claude(staged, home, launch=entry_launch)
        (config / "skills").mkdir(parents=True, exist_ok=True)
        paths = []
        for skill in sorted((home / ".claude" / "skills").iterdir()):
            shutil.copytree(skill, config / "skills" / skill.name)
            paths.append(f"skills/{skill.name}")
        server = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    target = config / ".claude.json"
    data = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
    data.setdefault("mcpServers", {})["tum"] = server["tum"]
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return paths


def install_codex_profile(staged: Path, home: Path, entry_launch) -> list[str]:
    skills = home / ".agents" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    paths = []
    for source in (staged / "skills").iterdir():
        shutil.copytree(source, skills / source.name)
        paths.append(f".agents/skills/{source.name}")
    entry = entry_launch.entry()
    lines = [
        "# Written by skill-lab for this lab profile only.",
        'approval_policy = "never"',
        "",
        "[mcp_servers.tum]",
        f"command = {toml_string(entry['command'])}",
        "args = [" + ", ".join(toml_string(arg) for arg in entry["args"]) + "]",
        "startup_timeout_sec = 60",
        "tool_timeout_sec = 900",
        "# The student approves campus reads; the filter has already removed account changes.",
        'default_tools_approval_mode = "approve"',
        "",
        "[mcp_servers.tum.env]",
        *(f"{key} = {toml_string(value)}" for key, value in entry.get("env", {}).items()),
        "",
    ]
    config = home / ".codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("\n".join(lines), encoding="utf-8")
    return paths + install_course_hooks(home)


def install_course_hooks(home: Path) -> list[str]:
    if not find_spec("tum_mcp.clients") or not find_spec("tum_mcp.clients.hook_config"):
        return []
    from tum_mcp.clients.codex_runtime import Runtime
    from tum_mcp.clients.hook_config import render, writes

    hosts = client_module("hosts")
    backend = hosts.StdioLaunch(
        sys.executable, ("-I", "-m", "tum_mcp", "serve"), hosts.storage_environment()
    )
    files, hooks = render("codex", home, backend)
    for name, body in files.items():
        path = home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    for change in writes("codex", home, hooks, {}):
        change.path.parent.mkdir(parents=True, exist_ok=True)
        change.path.write_bytes(change.after)
    (home / HOOK_MARKER).write_text(json.dumps(hooks))
    commands = {entry["hooks"][0]["command"] for entries in hooks.values() for entry in entries}
    runtime = Runtime(home)
    try:
        runtime.call(
            "initialize",
            {
                "clientInfo": {"name": "tum-mcp-skill-lab", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )

        def listing():
            return [
                hook
                for group in runtime.call("hooks/list", {"cwds": [str(home)]})["data"]
                for hook in group["hooks"]
                if hook.get("source") == "user"
                and Path(hook["sourcePath"]) == home / ".codex/hooks.json"
                and hook.get("command") in commands
            ]

        current = listing()
        if len(current) != len(commands) or any(not hook["enabled"] for hook in current):
            raise RuntimeError("The lab did not load the candidate's enabled course guards.")
        runtime.call(
            "config/batchWrite",
            {
                "edits": [
                    {
                        "keyPath": "hooks.state",
                        "value": {
                            hook["key"]: {"trusted_hash": hook["currentHash"]} for hook in current
                        },
                        "mergeStrategy": "upsert",
                    }
                ],
                "reloadUserConfig": True,
            },
        )
        if any(hook["trustStatus"] != "trusted" for hook in listing()):
            raise RuntimeError("The lab could not verify trust for its candidate course guards.")
    finally:
        runtime.close()
    return [*files, HOOK_MARKER]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=("claude", "codex"), required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--proxy", required=True)
    parser.add_argument("--block", default="")
    parser.add_argument("--downloads")
    args = parser.parse_args(argv)
    if args.downloads:
        os.environ["TUM_MOODLE_DOWNLOAD_DIR"] = args.downloads
    home = args.home.resolve()
    home.mkdir(parents=True, exist_ok=True)
    remove_previous(home)
    entry_launch = launch(args.proxy, args.block)
    with tempfile.TemporaryDirectory(prefix="skill-lab-stage-") as temporary:
        staged = Path(temporary)
        names = staged_skills(staged / "skills")
        if args.host == "claude":
            paths = install_claude_profile(staged, home, entry_launch)
        else:
            paths = install_codex_profile(staged, home, entry_launch)
    from tum_mcp import __version__

    (home / MARKER).write_text(
        json.dumps(
            {
                "host": args.host,
                "python": sys.executable,
                "tum_mcp_version": __version__,
                "skills": names,
                "paths": paths,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"skills": names, "python": sys.executable}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
