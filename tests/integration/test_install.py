import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import install as installer  # noqa: E402
import runtime_setup  # noqa: E402


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "user home"
    home.mkdir()
    for variable, value in {
        "HOME": home,
        "USERPROFILE": home,
        "LOCALAPPDATA": home / "AppData/Local",
        "XDG_DATA_HOME": home / ".local/share",
        "TUM_MOODLE_DATA_DIR": home / "private",
        "TUM_MOODLE_DOWNLOAD_DIR": home / "downloads",
    }.items():
        monkeypatch.setenv(variable, str(value))
    for folder, name, data in (
        (home / "private", "session.enc", b"encrypted-session"),
        (home / "downloads", "lecture.pdf", b"download-to-preserve"),
    ):
        folder.mkdir()
        (folder / name).write_bytes(data)
    catalog = home / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"name": "custom-local", "plugins": [{"name": "other"}]}))
    root = tmp_path / "checkout with spaces \u03a9"
    for folder in ("scripts", "plugin", "src", "docs"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    for filename in (
        "README.md",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "LICENSE",
        "NOTICE",
    ):
        shutil.copy2(ROOT / filename, root / filename)
    tools = tmp_path / "tools"
    tools.mkdir()
    program = (
        "import json, os, shutil, sys\nfrom pathlib import Path\n"
        "home = Path.home()\nargs = sys.argv[1:]\n"
        'with (home / "cli-events.jsonl").open("a") as out:\n'
        '    out.write(json.dumps(args) + "\\n")\n'
        'if os.environ.get("TEST_CLI_UNSUPPORTED"):\n    sys.exit(2)\n'
        'source = home / ".codex/plugins/local/tum-moodle"\n'
        'state = home / "fake-cli-version"\n'
        'if "--help" in args:\n    print("--json")\n'
        'elif "add" in args:\n'
        '    if os.environ.get("TEST_CLI_FAIL"):\n        sys.exit(1)\n'
        '    version = json.loads((source / "plugin.json").read_text())["version"]\n'
        '    cache = home / ".codex/plugins/cache/custom-local/tum-moodle" / version\n'
        "    if cache.exists():\n        shutil.rmtree(cache)\n"
        "    shutil.copytree(source, cache)\n"
        "    state.write_text(version)\n"
        '    print("{}")\n'
        "else:\n"
        "    entries = []\n"
        "    if state.exists():\n"
        '        entries.append({"pluginId": "tum-moodle@custom-local", '
        '"version": state.read_text(), '
        '"installed": True, "enabled": not bool(os.environ.get("TEST_CLI_DISABLED"))})\n'
        '    print(json.dumps({"installed": entries}))\n'
    )
    if os.name == "nt":
        script = tools / "codex_stub.py"
        script.write_text(program, encoding="utf-8")
        executable = tools / "codex.cmd"
        executable.write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        executable = tools / "codex"
        executable.write_text(f"#!{sys.executable}\n{program}", encoding="utf-8")
        executable.chmod(0o755)
    (tools / "google-chrome").write_text("synthetic-browser-marker")
    (tools / "google-chrome").chmod(0o755)
    monkeypatch.setattr(installer, "find_codex", lambda: str(executable))
    monkeypatch.setattr(installer, "chrome_available", lambda: True)
    return root


@pytest.fixture
def healthy_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        installer,
        "ensure_runtime",
        lambda *args, **kwargs: runtime_setup.RuntimeResult(False, None, {}),
    )


def test_install_refreshes_once_and_preserves_data(checkout: Path, healthy_runtime: None) -> None:
    first = installer.install(checkout)
    second = installer.install(checkout)
    assert first.status == "restart_required", first.message
    assert second.status == "ready", second.message
    events = [
        json.loads(line) for line in (Path.home() / "cli-events.jsonl").read_text().splitlines()
    ]
    assert sum("add" in event and "--help" not in event for event in events) == 1
    assert (
        Path(os.environ["TUM_MOODLE_DATA_DIR"]) / "session.enc"
    ).read_bytes() == b"encrypted-session"
    assert (
        Path(os.environ["TUM_MOODLE_DOWNLOAD_DIR"]) / "lecture.pdf"
    ).read_bytes() == b"download-to-preserve"
    catalog = json.loads((Path.home() / ".agents/plugins/marketplace.json").read_text())
    assert catalog["plugins"][0] == {"name": "other"}
    assert not (checkout / ".venv").exists()
    assert "Sign in" in second.next_actions[-2]
    assert "only if the user opts in" in second.next_actions[-1]


@pytest.mark.parametrize("problem", ["missing_cli", "unsupported_cli", "missing_chrome", "keyring"])
def test_action_required_preserves_completed_software_stages(
    checkout: Path, healthy_runtime: None, monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    match problem:
        case "missing_cli":
            monkeypatch.setattr(installer, "find_codex", lambda: None)
        case "unsupported_cli":
            monkeypatch.setenv("TEST_CLI_UNSUPPORTED", "1")
        case "missing_chrome":
            monkeypatch.setattr(installer, "chrome_available", lambda: False)
        case "keyring":
            monkeypatch.setattr(
                installer,
                "ensure_runtime",
                lambda *a, **k: runtime_setup.RuntimeResult(False, "Unlock the native store.", {}),
            )
    result = installer.install(checkout)
    assert result.status == "action_required"
    assert "runtime" in result.completed_stages
    assert "mcp_check" in result.completed_stages
    assert result.next_actions[-2:] == [installer.SIGN_IN, installer.COURSE_CHECK]


def test_failed_activation_does_not_claim_success(
    checkout: Path, healthy_runtime: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_CLI_FAIL", "1")
    result = installer.install(checkout)
    assert result.status == "error"
    assert result.failed_stage == "activation"
    assert "activation" not in result.completed_stages


def test_deleted_or_stale_cached_file_triggers_refresh(
    checkout: Path, healthy_runtime: None
) -> None:
    assert installer.install(checkout).status == "restart_required"
    version = (Path.home() / "fake-cli-version").read_text()
    cache = Path.home() / ".codex/plugins/cache/custom-local/tum-moodle" / version
    (cache / "old-skill.txt").write_text("obsolete")
    assert installer.install(checkout).status == "restart_required"
    assert not (cache / "old-skill.txt").exists()


@pytest.mark.parametrize(
    "status,exit_code",
    [("ready", 0), ("restart_required", 0), ("action_required", 2), ("error", 1)],
)
def test_json_output_is_a_single_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], status: str, exit_code: int
) -> None:
    monkeypatch.setattr(sys, "argv", ["install.py", "--json"])
    monkeypatch.setattr(
        installer, "install", lambda **kwargs: installer.InstallResult(status, [], [], {})
    )
    assert installer.main() == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_runtime_cache_checks_content_and_repairs(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []
    runtime = runtime_setup.runtime_python()
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    monkeypatch.setattr(runtime_setup, "find_uv", lambda: "/test/uv")
    monkeypatch.setenv("VIRTUAL_ENV", "unrelated-environment")

    def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "sync" in command:
            assert "VIRTUAL_ENV" not in kwargs["env"]
            assert kwargs["env"]["UV_PROJECT_ENVIRONMENT"] == str(runtime.parent.parent)
            assert {"--locked", "--no-dev", "--no-editable"} <= set(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"python": "3.13", "tools": 16, "keyring_error": None})
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert runtime_setup.ensure_runtime(checkout).changed
    assert not runtime_setup.ensure_runtime(checkout).changed
    assert "--check" in commands[-2]
    source = checkout / "src/tum_moodle/__init__.py"
    metadata = (checkout / "pyproject.toml").stat()
    source.write_text(source.read_text() + "\nINSTALLED_SOURCE_MARKER = 1\n")
    os.utime(checkout / "pyproject.toml", ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    assert runtime_setup.ensure_runtime(checkout).changed
    assert "--reinstall-package" in commands[-2]
    (checkout / "uv.lock").write_text((checkout / "uv.lock").read_text() + "\n")
    assert runtime_setup.ensure_runtime(checkout).changed
    assert runtime_setup.ensure_runtime(checkout, repair=True).changed
    assert "--reinstall" in commands[-2]
    (runtime_setup.app_root() / "runtime-install.json").write_text("broken")
    assert runtime_setup.ensure_runtime(checkout).changed


def test_failed_health_check_invalidates_receipt(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = runtime_setup.runtime_python()
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    receipt = runtime_setup.app_root() / "runtime-install.json"
    receipt.write_text("{}")
    monkeypatch.setattr(runtime_setup, "find_uv", lambda: "/test/uv")

    def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        if "sync" not in command:
            raise subprocess.CalledProcessError(1, command, stderr="Broken runtime")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        runtime_setup.ensure_runtime(checkout)
    assert not receipt.exists()


def test_runtime_setup_finds_intel_homebrew(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(Path, "is_file", lambda path: path == Path("/usr/local/bin/uv"))
    assert runtime_setup.find_uv() == "/usr/local/bin/uv"


def test_missing_uv_is_actionable_before_installing(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installer, "find_uv", lambda: None)
    result = installer.install(checkout)
    assert result.status == "action_required"
    assert result.completed_stages == []
    assert not (Path.home() / ".codex/plugins/local/tum-moodle").exists()


def test_malformed_cli_response_is_a_manual_action(
    checkout: Path, healthy_runtime: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "invalid json"),
    )
    result = installer.install(checkout)
    assert result.status == "action_required"
    assert "cannot verify activation" in result.next_actions[0]


def test_sync_failure_does_not_create_a_receipt(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_setup, "find_uv", lambda: "/test/uv")

    def fail(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        runtime_setup.ensure_runtime(checkout)
    assert not (runtime_setup.app_root() / "runtime-install.json").exists()


def test_real_cold_warm_source_update_and_repair(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.environ.get("TUM_MOODLE_INSTALLER_INTEGRATION") != "1":
        pytest.skip(
            "Set TUM_MOODLE_INSTALLER_INTEGRATION=1 for isolated real downloads/runtime checks."
        )
    isolated = checkout.parent / "cold cache"
    monkeypatch.setenv("UV_CACHE_DIR", str(isolated / "uv"))
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(isolated / "python"))
    monkeypatch.setenv("UV_PYTHON_PREFERENCE", "only-managed")
    cold = installer.install(checkout)
    assert cold.status == "restart_required", cold.message or cold.next_actions
    runtime = runtime_setup.runtime_python()
    assert runtime.is_file()
    assert (isolated / "python").is_dir()

    monkeypatch.setenv("UV_OFFLINE", "1")
    warm = installer.install(checkout)
    assert warm.status == "ready", warm.message
    assert warm.timings["runtime_sync"] < 0.01

    source = checkout / "src/tum_moodle/__init__.py"
    source.write_text(source.read_text() + '\nINSTALLER_SOURCE_TEST = "changed"\n')
    updated = installer.install(checkout)
    assert updated.status == "restart_required", updated.message
    probe = subprocess.run(
        [str(runtime), "-c", "import tum_moodle; print(tum_moodle.INSTALLER_SOURCE_TEST)"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip() == "changed"
    location = subprocess.run(
        [str(runtime), "-c", "import tum_moodle.server; print(tum_moodle.server.__file__)"],
        check=True,
        capture_output=True,
        text=True,
    )
    Path(location.stdout.strip()).write_text('raise RuntimeError("synthetic broken install")\n')
    broken = installer.install(checkout)
    assert broken.status == "error"
    assert broken.failed_stage == "runtime"
    repaired = installer.install(checkout, repair=True)
    assert repaired.status == "restart_required", repaired.message
    assert not (checkout / ".venv").exists()
    assert (
        Path(os.environ["TUM_MOODLE_DATA_DIR"]) / "session.enc"
    ).read_bytes() == b"encrypted-session"
    assert (
        Path(os.environ["TUM_MOODLE_DOWNLOAD_DIR"]) / "lecture.pdf"
    ).read_bytes() == b"download-to-preserve"
    receipt = json.loads((runtime_setup.app_root() / "runtime-install.json").read_text())
    assert receipt["checkout"] == str(checkout.resolve())
    checkout.rename(checkout.parent / "moved checkout")
    bootstrap = Path.home() / ".codex/plugins/local/tum-moodle/scripts/bootstrap.py"
    detached = subprocess.run(
        [str(runtime), str(bootstrap)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(detached.stdout)["changed"] is False
    measurement = {
        "platform": sys.platform,
        "cold_isolation": ["private runtime", "uv cache", "managed Python cache"],
        "activation": "synthetic Codex CLI; real uv, interpreter, dependencies, and MCP",
        "cold": cold.timings,
        "warm_offline": warm.timings,
        "source_update_offline": updated.timings,
        "repair_offline": repaired.timings,
    }
    evidence = os.environ.get("TUM_MOODLE_INSTALLER_EVIDENCE")
    if evidence:
        target = Path(evidence)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(measurement, indent=2) + "\n", encoding="utf-8")
