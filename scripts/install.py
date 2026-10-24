# /// script
# requires-python = ">=3.13,<3.14"
# dependencies = []
# ///
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, Literal, assert_never

from package_plugin import build_package, register_package

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin/scripts"))
sys.path.insert(0, str(ROOT / "src"))
from runtime_setup import ensure_runtime, find_uv, same_package  # noqa: E402

from tum_moodle.browsers import BrowserSetupError, discover_browsers  # noqa: E402

SIGN_IN: Final = (
    'Prompt the user: "Sign in to TUM Moodle." Use native tools after any reload; '
    "reuse an already connected session. Credentials and MFA stay in the browser."
)
COURSE_CHECK: Final = (
    "After connection succeeds, offer an optional current-semester course check. "
    "List courses only if the user opts in."
)


@dataclass(frozen=True, slots=True)
class InstallResult:
    status: Literal["ready", "restart_required", "action_required", "error"]
    completed_stages: list[str]
    next_actions: list[str]
    timings: dict[str, float]
    failed_stage: str | None = None
    message: str | None = None
    schema_version: int = field(default=1, init=False)


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


def chrome_available() -> bool:
    """Compatibility name for the legacy installer; use shared Chromium discovery."""
    try:
        return bool(discover_browsers())
    except BrowserSetupError:
        return False


def plugin_current(executable: str, marketplace: str, package: Path) -> bool | None:
    result = subprocess.run(
        [executable, "plugin", "list", "--marketplace", marketplace, "--json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        return None
    try:
        listing = json.loads(result.stdout)
        entries = listing["installed"]
        for entry in entries:
            if entry["pluginId"] == f"tum-moodle@{marketplace}":
                version = entry["version"]
                if not isinstance(version, str) or Path(version).name != version:
                    return None
                cache = Path.home() / ".codex/plugins/cache" / marketplace / "tum-moodle" / version
                return (
                    entry["installed"] is True
                    and entry["enabled"] is True
                    and same_package(package, cache)
                )
    except (ValueError, KeyError, TypeError):
        return None
    return False


def install(root: Path = ROOT, *, repair: bool = False) -> InstallResult:
    started = time.perf_counter()
    completed: list[str] = []
    actions: list[str] = []
    timings: dict[str, float] = {}
    stage = "prerequisites"
    try:
        if find_uv() is None:
            return InstallResult(
                "action_required",
                [],
                ["Install uv from https://docs.astral.sh/uv/ and retry."],
                {"total": round(time.perf_counter() - started, 3)},
            )
        chrome_missing = not chrome_available()
        if chrome_missing:
            actions.append(
                "Install a Chromium browser before TUM sign-in; see docs/setup.md for this OS."
            )
        completed.append(stage)
        stage = "packaging"
        print("Preparing the local plugin...", file=sys.stderr, flush=True)
        package = build_package(root)
        source = Path.home() / ".codex/plugins/local/tum-moodle"
        source_changed = not same_package(package, source)
        catalog = register_package(package, replace_source=source_changed)
        marketplace = json.loads(catalog.read_text(encoding="utf-8"))["name"]
        if (
            not isinstance(marketplace, str)
            or not marketplace
            or Path(marketplace).name != marketplace
        ):
            raise ValueError("The personal marketplace has an invalid name.")
        timings[stage] = round(time.perf_counter() - started, 3)
        completed.append(stage)
        stage = "runtime"
        print("Checking the private runtime and MCP server...", file=sys.stderr, flush=True)
        runtime = ensure_runtime(source, repair=repair, checkout=root)
        timings.update(runtime.timings)
        completed.extend([stage, "mcp_check"])
        if runtime.keyring_error:
            actions.append(runtime.keyring_error)
        stage = "activation"
        activation_started = time.perf_counter()
        executable = find_codex()
        refreshed = False
        current = plugin_current(executable, marketplace, package) if executable else None
        if current is None:
            actions.append(
                "Install/enable TUM Moodle from your personal source in Codex Plugins, "
                "then fully quit and reopen Codex. This CLI cannot verify activation."
            )
        else:
            if not current:
                help_result = subprocess.run(
                    [executable, "plugin", "add", "--help"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if help_result.returncode or "--json" not in help_result.stdout:
                    actions.append(
                        "Install/enable TUM Moodle in Codex Plugins, then fully restart Codex."
                    )
                else:
                    subprocess.run(
                        [executable, "plugin", "add", f"tum-moodle@{marketplace}", "--json"],
                        check=True,
                        stdout=sys.stderr,
                        stderr=sys.stderr,
                        timeout=60,
                    )
                    if plugin_current(executable, marketplace, package) is not True:
                        raise ValueError(
                            "Codex did not confirm the current plugin is installed and enabled."
                        )
                    refreshed = True
                    completed.append(stage)
            else:
                completed.append(stage)
        timings[stage] = round(time.perf_counter() - activation_started, 3)
        changed = source_changed or runtime.changed or refreshed
        if changed and stage in completed:
            actions.append("Fully quit and reopen Codex once to load the installed plugin.")
        status: Literal["ready", "restart_required", "action_required", "error"]
        status = (
            "action_required"
            if chrome_missing or runtime.keyring_error or stage not in completed
            else "restart_required"
            if changed
            else "ready"
        )
        actions.extend([SIGN_IN, COURSE_CHECK])
        timings["total"] = round(time.perf_counter() - started, 3)
        return InstallResult(status, completed, actions, timings)
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError) as error:
        detail = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            detail += "\n" + str(error.stderr)[-2000:]
        timings["total"] = round(time.perf_counter() - started, 3)
        return InstallResult(
            "error",
            completed,
            ["Fix the reported issue, then retry. Use --repair for a broken runtime."],
            timings,
            stage,
            detail,
        )


def main() -> int:
    arguments = set(sys.argv[1:])
    if arguments - {"--json", "--repair", "--help"}:
        print("Usage: uv run scripts/install.py [--json] [--repair]", file=sys.stderr)
        return 1
    if "--help" in arguments:
        print("Usage: uv run scripts/install.py [--json] [--repair]")
        return 0
    result = install(repair="--repair" in arguments)
    if "--json" in arguments:
        print(json.dumps(asdict(result)))
    else:
        print(f"TUM Moodle: {result.status.replace('_', ' ')}")
        if result.message:
            print(f"{result.failed_stage}: {result.message}", file=sys.stderr)
        for action in result.next_actions:
            print(action)
    match result.status:
        case "error":
            return 1
        case "action_required":
            return 2
        case "ready" | "restart_required":
            return 0
        case unreachable:
            assert_never(unreachable)


if __name__ == "__main__":
    raise SystemExit(main())
