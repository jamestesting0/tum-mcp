# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if "--help" in sys.argv[1:]:
        print("Usage: uv run scripts/update.py [--json] [--repair]")
        return 0
    if set(sys.argv[1:]) - {"--json", "--repair"}:
        print("Unknown update option. Use --help.", file=sys.stderr)
        return 1
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
        print("Pulling the latest code...", file=sys.stderr, flush=True)
        subprocess.run(
            [git, "pull", "--ff-only"],
            cwd=root,
            check=True,
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
        stage = "installing the update"
        return subprocess.run(
            [sys.executable, str(root / "scripts/install.py"), *sys.argv[1:]],
            cwd=root,
            check=False,
        ).returncode
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as error:
        print(f"Update stopped while {stage}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
