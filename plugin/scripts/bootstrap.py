import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
uv = shutil.which("uv") or next(
    (
        str(path)
        for path in (
            Path.home() / ".local/bin/uv",
            Path("/opt/homebrew/bin/uv"),
            Path("/usr/local/bin/uv"),
        )
        if path.is_file()
    ),
    None,
)
if uv is None:
    sys.exit("Install uv from https://docs.astral.sh/uv/ and run setup again.")
environment = os.environ.copy()
environment["UV_PROJECT_ENVIRONMENT"] = str(
    Path.home() / "Library/Application Support/TUMMoodle/runtime"
)
subprocess.run(
    [
        uv,
        "sync",
        "--locked",
        "--directory",
        str(root),
        "--python",
        "3.13",
        "--no-dev",
        "--no-editable",
    ],
    env=environment,
    check=True,
)
