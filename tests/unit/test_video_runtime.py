import json
import subprocess
from pathlib import Path

import pytest

from tum_mcp import video_runtime as runtime
from tum_mcp.errors import CampusError


@pytest.mark.parametrize(
    ("system", "machine", "mac", "libc", "expected"),
    [
        ("Windows", "AMD64", "", ("", ""), True),
        ("Windows", "ARM64", "", ("", ""), False),
        ("Darwin", "arm64", "15.7", ("", ""), True),
        ("Darwin", "arm64", "13.6", ("", ""), False),
        # moderngl/glcontext publish no Intel macOS or Linux ARM64 wheels for CPython 3.13.
        ("Darwin", "x86_64", "14.1", ("", ""), False),
        ("Linux", "x86_64", "", ("glibc", "2.35"), True),
        ("Linux", "aarch64", "", ("glibc", "2.35"), False),
        ("Linux", "x86_64", "", ("glibc", "2.17"), False),
        ("Linux", "x86_64", "", ("musl", "1.2"), False),
    ],
)
def test_supported_hosts(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
    mac: str,
    libc: tuple[str, str],
    expected: bool,
) -> None:
    monkeypatch.setattr("platform.system", lambda: system)
    monkeypatch.setattr("platform.machine", lambda: machine)
    monkeypatch.setattr("platform.mac_ver", lambda: (mac, ("", "", ""), ""))
    monkeypatch.setattr("platform.libc_ver", lambda: libc)
    ok, reason = runtime.supported()
    assert ok is expected
    assert bool(reason) is not expected


def test_linux_prerequisites_name_exact_packages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    folder = tmp_path / "pkgconfig"
    folder.mkdir()
    (folder / "cairo.pc").write_text("")
    monkeypatch.setattr(runtime, "pkg_config_path", lambda: [str(folder)])
    monkeypatch.setattr("shutil.which", lambda name: None)
    missing, commands = runtime.prerequisites()
    assert missing == ("libpango1.0-dev", "build-essential")
    assert commands[0] == "sudo apt install libpango1.0-dev build-essential"


def test_macos_prerequisites_only_need_cairo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr(runtime, "_homebrew", lambda: tmp_path)
    monkeypatch.setattr(runtime, "pkg_config_path", lambda: [str(tmp_path)])
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/clang")
    missing, commands = runtime.prerequisites()
    assert missing == ("cairo",) and commands == ("brew install cairo",)
    (tmp_path / "cairo.pc").write_text("")
    assert runtime.prerequisites() == ((), ())


def test_lock_versions_and_identity_ignore_helper_code() -> None:
    versions = runtime.expected_versions()
    assert versions["manim"] == "0.22.0" and versions["pkgconf"]
    assert "colorama" not in versions or runtime.platform.system() == "Windows"
    assert runtime.render_profile().startswith(runtime.profile() + "-")
    lock = runtime.lock_path().read_text(encoding="utf-8")
    assert "--hash=sha256:" in lock and "manim==0.22.0" in lock
    assert runtime.SOURCE_BUILDS == {"pycairo", "manimpango", "srt"}


def test_worker_gets_a_scrubbed_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GH_TOKEN", "sentinel-secret")
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    seen: dict = {}

    def run(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess:
        seen.update(options)
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, json.dumps({"ok": True}).encode(), b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert runtime.call_worker({"action": "health"}, executable=tmp_path / "python") == {"ok": True}
    environment = seen["env"]
    assert "GH_TOKEN" not in environment and "TUM_MCP_DATA_DIR" not in environment
    assert seen["argv"][1] == "-I" and seen["argv"][2].endswith("worker.py")
    assert "sentinel-secret" not in json.dumps(seen, default=str)


def test_worker_failures_are_typed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def crash(argv: tuple[str, ...], **_: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 1, b"", b"Traceback\nImportError: cairo\n")

    monkeypatch.setattr(subprocess, "run", crash)
    with pytest.raises(CampusError, match="ImportError: cairo"):
        runtime.call_worker({"action": "health"}, executable=tmp_path / "python")

    def slow(argv: tuple[str, ...], **_: object) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(CampusError, match="resumable"):
        runtime.call_worker({"action": "health"}, executable=tmp_path / "python", timeout=1)


def test_install_stops_on_missing_prerequisites(monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = runtime.RuntimeStatus(
        supported=True,
        installed=False,
        profile="x",
        reason="prerequisites_missing",
        missing=("cairo",),
        commands=("brew install cairo",),
    )
    monkeypatch.setattr(runtime, "status", lambda: blocked)
    with pytest.raises(CampusError, match="brew install cairo"):
        runtime.install()
