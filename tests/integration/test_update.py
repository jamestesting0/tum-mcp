import json
import os
import runpy
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True, slots=True)
class Installation:
    local: Path
    seed: Path
    environment: dict[str, str]


def git(path: Path, arguments: list[str], environment: dict[str, str]) -> str:
    executable = shutil.which("git")
    assert executable is not None
    result = subprocess.run(
        [executable, "-C", str(path), *arguments],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_update(installation: Installation, **overrides: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(installation.local / "scripts/update.py")],
        cwd=installation.local.parent,
        env={**installation.environment, **overrides},
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def installation(tmp_path: Path) -> Installation:
    source = Path(__file__).resolve().parents[2]
    home = tmp_path / "user home"
    tools = tmp_path / "tools"
    tools.mkdir()
    home.mkdir()
    environment = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "LOCALAPPDATA": str(home / "AppData/Local"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "TUM_MOODLE_DATA_DIR": str(home / "moodle data"),
        "TUM_MOODLE_DOWNLOAD_DIR": str(home / "moodle downloads"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "UPDATE_TEST_LOG": str(tmp_path / "events.jsonl"),
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
    }
    remote = tmp_path / "remote.git"
    git(tmp_path, ["init", "--bare", "--initial-branch=main", str(remote)], environment)
    seed = tmp_path / "seed"
    git(tmp_path, ["clone", str(remote), str(seed)], environment)
    git(seed, ["config", "user.name", "Updater test"], environment)
    git(seed, ["config", "user.email", "updater@example.invalid"], environment)
    for folder in ("scripts", "plugin", "src", "docs"):
        shutil.copytree(
            source / folder, seed / folder, ignore=shutil.ignore_patterns("__pycache__")
        )
    for filename in (
        "README.md",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "LICENSE",
        "NOTICE",
        ".gitignore",
    ):
        shutil.copy2(source / filename, seed / filename)
    (seed / "plugin/scripts/bootstrap.py").write_text(
        "import os, sys\nfrom pathlib import Path\n"
        'with Path(os.environ["UPDATE_TEST_LOG"]).open("a") as output:\n'
        '    output.write("bootstrap\\n")\n'
        'sys.exit(int(os.environ.get("UPDATE_TEST_BOOTSTRAP_FAIL", "0")))\n',
        encoding="utf-8",
    )
    git(seed, ["add", "."], environment)
    git(seed, ["commit", "-m", "Initial installation"], environment)
    git(seed, ["push", "-u", "origin", "main"], environment)
    local = tmp_path / "local checkout"
    git(tmp_path, ["clone", str(remote), str(local)], environment)
    git(local, ["config", "user.name", "Updater test"], environment)
    git(local, ["config", "user.email", "updater@example.invalid"], environment)
    (seed / "README.md").write_text("Updated upstream content.\n", encoding="utf-8")
    git(seed, ["commit", "-am", "Update available"], environment)
    git(seed, ["push"], environment)

    catalog = home / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"name": "custom-local", "plugins": [{"name": "existing"}]}))
    data = Path(environment["TUM_MOODLE_DATA_DIR"])
    downloads = Path(environment["TUM_MOODLE_DOWNLOAD_DIR"])
    data.mkdir()
    downloads.mkdir()
    (data / "session.enc").write_bytes(b"existing-encrypted-session")
    (downloads / "lecture.pdf").write_bytes(b"existing-download")
    program = (
        "import json, os, sys\nfrom pathlib import Path\n"
        'with Path(os.environ["UPDATE_TEST_LOG"]).open("a") as output:\n'
        '    output.write(json.dumps(sys.argv[1:]) + "\\n")\n'
        'sys.exit(int(os.environ.get("UPDATE_TEST_CODEX_FAIL", "0")))\n'
    )
    if os.name == "nt":
        python_file = tools / "codex_stub.py"
        python_file.write_text(program, encoding="utf-8")
        (tools / "codex.cmd").write_text(f'@"{sys.executable}" "{python_file}" %*\n')
    else:
        executable = tools / "codex"
        executable.write_text(f"#!{sys.executable}\n" + program, encoding="utf-8")
        executable.chmod(0o755)
    return Installation(local, seed, environment)


def test_update_fast_forwards_rebuilds_and_refreshes_the_custom_marketplace(
    installation: Installation,
) -> None:
    result = run_update(installation)

    assert result.returncode == 0, result.stdout + result.stderr
    assert git(installation.local, ["rev-parse", "HEAD"], installation.environment) == git(
        installation.seed, ["rev-parse", "HEAD"], installation.environment
    )
    events = Path(installation.environment["UPDATE_TEST_LOG"]).read_text().splitlines()
    assert events == [
        "bootstrap",
        json.dumps(["plugin", "add", "tum-moodle@custom-local", "--json"]),
    ]
    home = Path(installation.environment["HOME"])
    catalog = json.loads((home / ".agents/plugins/marketplace.json").read_text())
    assert catalog["plugins"][0] == {"name": "existing"}
    assert (
        home / ".codex/plugins/local/tum-moodle/README.md"
    ).read_text() == "Updated upstream content.\n"
    data = Path(installation.environment["TUM_MOODLE_DATA_DIR"])
    downloads = Path(installation.environment["TUM_MOODLE_DOWNLOAD_DIR"])
    assert (data / "session.enc").read_bytes() == b"existing-encrypted-session"
    assert (downloads / "lecture.pdf").read_bytes() == b"existing-download"
    assert git(installation.local, ["status", "--porcelain"], installation.environment) == ""


@pytest.mark.parametrize("filename", ["README.md", "untracked-notes.txt"])
def test_dirty_checkout_is_preserved_without_installing(
    installation: Installation, filename: str
) -> None:
    path = installation.local / filename
    path.write_text("Local work to preserve.\n", encoding="utf-8")
    before = git(installation.local, ["rev-parse", "HEAD"], installation.environment)

    result = run_update(installation)

    assert result.returncode == 1
    assert path.read_text() == "Local work to preserve.\n"
    assert git(installation.local, ["rev-parse", "HEAD"], installation.environment) == before
    assert not Path(installation.environment["UPDATE_TEST_LOG"]).exists()


def test_diverged_history_is_not_merged_or_installed(installation: Installation) -> None:
    (installation.local / "README.md").write_text("Local committed work.\n", encoding="utf-8")
    git(installation.local, ["commit", "-am", "Local change"], installation.environment)
    before = git(installation.local, ["rev-parse", "HEAD"], installation.environment)

    result = run_update(installation)

    assert result.returncode == 1
    assert git(installation.local, ["rev-parse", "HEAD"], installation.environment) == before
    assert not (installation.local / ".git/MERGE_HEAD").exists()
    assert not Path(installation.environment["UPDATE_TEST_LOG"]).exists()


@pytest.mark.parametrize("failure", ["UPDATE_TEST_BOOTSTRAP_FAIL", "UPDATE_TEST_CODEX_FAIL"])
def test_failed_install_step_returns_failure(installation: Installation, failure: str) -> None:
    result = run_update(installation, **{failure: "1"})

    assert result.returncode == 1
    events = Path(installation.environment["UPDATE_TEST_LOG"]).read_text().splitlines()
    assert events[0] == "bootstrap"
    if failure == "UPDATE_TEST_BOOTSTRAP_FAIL":
        assert events == ["bootstrap"]


def test_missing_codex_prints_manual_refresh_step(
    installation: Installation, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    for key, value in installation.environment.items():
        monkeypatch.setenv(key, value)
    namespace = runpy.run_path(str(installation.local / "scripts/update.py"))
    main = namespace["main"]
    monkeypatch.setitem(main.__globals__, "find_codex", lambda: None)

    assert main() == 0

    assert "Reinstall TUM Moodle" in capfd.readouterr().out
    assert Path(installation.environment["UPDATE_TEST_LOG"]).read_text() == "bootstrap\n"
