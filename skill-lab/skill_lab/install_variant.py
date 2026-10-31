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
from pathlib import Path

MARKER = ".skill-lab-install.json"


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


def launch(proxy: str, block: str):
    from tum_mcp.client_hosts import StdioLaunch, storage_environment

    backend = (sys.executable, "-I", "-m", "tum_mcp", "serve")
    return StdioLaunch(
        sys.executable, ("-I", proxy, "--block", block, "--", *backend), storage_environment()
    )


def remove_previous(home: Path) -> None:
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
    from tum_mcp.client_rendering import install_claude

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
    return paths


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
