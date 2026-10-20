# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_codex() -> str | None:
    executable = shutil.which("codex")
    if executable:
        return executable
    for folder in (Path("/Applications"), Path.home() / "Applications"):
        for relative in (
            "Codex.app/Contents/Resources/codex",
            "Codex.app/Contents/Resources/codex-cli/bin/codex",
            "ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
        ):
            candidate = folder / relative
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    git = shutil.which("git")
    if git is None:
        print("Update stopped: install Git first.", file=sys.stderr)
        return 1
    stage = "checking the checkout"
    try:
        checkout = subprocess.run(
            [git, "rev-parse", "--show-toplevel"],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        if Path(checkout).resolve() != root:
            print(
                "Update stopped: run this script from its original Git checkout.",
                file=sys.stderr,
            )
            return 1
        dirty = subprocess.run(
            [git, "status", "--porcelain"],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        if dirty:
            print(
                "Update stopped: the checkout has local changes. "
                "Commit or stash them before updating.",
                file=sys.stderr,
            )
            return 1

        stage = "pulling the latest code"
        print("Pulling the latest code...", flush=True)
        subprocess.run([git, "pull", "--ff-only"], cwd=root, check=True)
        stage = "rebuilding the plugin"
        print("Rebuilding the plugin...", flush=True)
        subprocess.run(
            [sys.executable, str(root / "scripts/package_plugin.py"), "--register"],
            cwd=root,
            check=True,
        )
        stage = "updating the runtime"
        print("Updating the runtime...", flush=True)
        bootstrap = Path.home() / ".codex/plugins/local/tum-moodle/scripts/bootstrap.py"
        subprocess.run([sys.executable, str(bootstrap)], cwd=root, check=True)

        executable = find_codex()
        if executable is None:
            print(
                "Code and runtime updated. Reinstall TUM Moodle from your personal source "
                "in Plugins, then fully restart Codex."
            )
            return 0
        stage = "refreshing Codex"
        print("Refreshing Codex...", flush=True)
        marketplace_path = Path.home() / ".agents/plugins/marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        subprocess.run(
            [executable, "plugin", "add", f"tum-moodle@{marketplace['name']}", "--json"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as error:
        print(f"Update stopped while {stage}: {error}", file=sys.stderr)
        return 1
    print("TUM Moodle updated. Fully quit and reopen Codex to load the update.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
