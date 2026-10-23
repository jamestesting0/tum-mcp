import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if not (root / "pyproject.toml").is_file():
    root = root.parent
sys.path.insert(0, str(root / "src"))
from tum_moodle.platforms import app_root, runtime_python  # noqa: E402


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    changed: bool
    keyring_error: str | None
    timings: dict[str, float]


def find_uv() -> str | None:
    return shutil.which("uv") or next(
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


def files_under(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def digest(folder: Path, paths: list[Path]) -> str:
    hasher = hashlib.sha256()
    for path in paths:
        hasher.update(path.relative_to(folder).as_posix().encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def same_package(expected: Path, installed: Path) -> bool:
    expected_files = files_under(expected)
    if {path.relative_to(expected) for path in expected_files} != {
        path.relative_to(installed) for path in files_under(installed)
    }:
        return False
    for path in expected_files:
        destination = installed / path.relative_to(expected)
        if not destination.is_file() or destination.read_bytes() != path.read_bytes():
            return False
    return installed.is_dir()


def ensure_runtime(
    package: Path, *, repair: bool = False, checkout: Path | None = None
) -> RuntimeResult:
    uv = find_uv()
    if uv is None:
        raise FileNotFoundError("Install uv from https://docs.astral.sh/uv/ and retry setup.")
    started = time.perf_counter()
    runtime = runtime_python()
    fingerprint = {
        "schema_version": 1,
        "runtime": str(runtime),
        "python": "3.13",
        "platform": sys.platform,
        "architecture": platform.machine(),
        "project": digest(package, [package / "pyproject.toml", package / "uv.lock"]),
        "source": digest(package, files_under(package / "src")),
    }
    receipt_path = app_root() / "runtime-install.json"
    try:
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    previous_identity = (
        {key: value for key, value in previous.items() if key != "checkout"}
        if isinstance(previous, dict)
        else None
    )
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    environment["UV_PROJECT_ENVIRONMENT"] = str(runtime.parent.parent)
    command = [
        uv,
        "sync",
        "--locked",
        "--directory",
        str(package),
        "--python",
        "3.13",
        "--no-dev",
        "--no-editable",
    ]
    unchanged = not repair and previous_identity == fingerprint and runtime.is_file()
    if unchanged:
        unchanged = (
            subprocess.run(
                [*command, "--check", "--offline"],
                env=environment,
                stdout=sys.stderr,
                stderr=sys.stderr,
                timeout=30,
                check=False,
            ).returncode
            == 0
        )
    checked_at = time.perf_counter()
    if not unchanged:
        app_root().mkdir(mode=0o700, parents=True, exist_ok=True)
        refresh = ["--reinstall"] if repair else ["--reinstall-package", "tum-moodle-integration"]
        subprocess.run(
            [*command, *refresh],
            env=environment,
            check=True,
            stdout=sys.stderr,
            stderr=sys.stderr,
            timeout=600,
        )
    synced_at = time.perf_counter()
    try:
        result = subprocess.run(
            [str(runtime), str(package / "scripts/check_runtime.py")],
            check=True,
            capture_output=True,
            text=True,
            timeout=40,
        )
        health = json.loads(result.stdout)
        if health["python"] != "3.13" or health["tools"] < 5:
            raise ValueError("Unexpected runtime or missing MCP tools. Retry with --repair.")
        keyring_error = health["keyring_error"]
        if keyring_error is not None and not isinstance(keyring_error, str):
            raise ValueError("Invalid runtime health response.")
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
        receipt_path.unlink(missing_ok=True)
        raise
    recorded_checkout = (
        str(checkout.resolve())
        if checkout
        else (previous.get("checkout") if isinstance(previous, dict) else None)
    )
    payload = json.dumps({**fingerprint, "checkout": recorded_checkout}, indent=2) + "\n"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != payload:
        temporary = receipt_path.with_suffix(".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(receipt_path)
    return RuntimeResult(
        changed=not unchanged,
        keyring_error=keyring_error,
        timings={
            "runtime_check": round(checked_at - started, 3),
            "runtime_sync": round(synced_at - checked_at, 3),
            "mcp_check": round(time.perf_counter() - synced_at, 3),
        },
    )
