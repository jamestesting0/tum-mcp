import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from tum_moodle.platforms import app_root  # noqa: E402

uv = shutil.which("uv") or next(
    (
        str(path)
        for path in (
            Path.home() / ".local/bin/uv",
            Path.home() / ".local/bin/uv.exe",
            Path("/opt/homebrew/bin/uv"),
            Path("/usr/local/bin/uv"),
        )
        if path.is_file()
    ),
    None,
)
if uv is None:
    sys.exit("Install uv from https://docs.astral.sh/uv/ and run setup again.")
if os.name == "nt" and sys.version_info < (3, 13):
    subprocess.run([uv, "run", "--no-project", "--python", "3.13", __file__], check=True)
    sys.exit()
app_root().mkdir(mode=0o700, parents=True, exist_ok=True)
environment = os.environ.copy()
environment.pop("VIRTUAL_ENV", None)
environment["UV_PROJECT_ENVIRONMENT"] = str(app_root() / "runtime")
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
print("TUM Moodle is ready. Install/enable it from your personal source in Plugins.")
print("Then ask Codex to sign in to TUM Moodle. Complete sign-in and MFA only in Chrome.")
