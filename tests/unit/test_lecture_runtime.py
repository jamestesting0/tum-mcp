import sys
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.lecture_processing import runtime
from tum_mcp.lecture_processing.runtime_process import isolated_run


@pytest.mark.parametrize(
    "system,machine", [("Windows", "ARM64"), ("Linux", "aarch64"), ("Darwin", "x86_64")]
)
def test_unsupported_host_does_not_attempt_install(
    system: str, machine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: system)
    monkeypatch.setattr(runtime.platform, "machine", lambda: machine)
    assert not runtime.status().supported
    with pytest.raises(CampusError, match="Timed captions remain"):
        runtime.install()


def test_status_does_not_create_models_or_download_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    assert not runtime.status().installed
    assert not (tmp_path / "lecture-runtime").exists()


def test_worker_environment_omits_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAMPUS_COOKIE", "synthetic-secret-sentinel")
    assert (
        isolated_run(
            (
                sys.executable,
                "-I",
                "-c",
                "import os;print(os.environ.get('CAMPUS_COOKIE','absent'))",
            )
        )
        == b"absent\n"
    )


def test_hung_worker_is_terminated_and_diagnostics_are_private() -> None:
    with pytest.raises(CampusError, match="timed out"):
        isolated_run((sys.executable, "-I", "-c", "import time;time.sleep(10)"), timeout=1)


def test_failed_runtime_install_preserves_previous_user_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runtime, "supported", lambda: True)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: sys.executable)

    def fail(*args, **kwargs):
        raise CampusError(runtime.Code.OFFLINE, "Synthetic install failure")

    monkeypatch.setattr(runtime, "isolated_run", fail)
    keep = tmp_path / "user-notes.txt"
    keep.write_text("keep")
    with pytest.raises(CampusError, match="Synthetic install failure"):
        runtime.install()
    assert keep.read_text() == "keep"
    assert not runtime.runtime_root().exists()
    assert not list(runtime.runtime_root().parent.glob("lecture-install-*"))


def test_optional_install_reuses_the_launchers_verified_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import json

    from tum_mcp.lecture_processing.installer_uv import installer_uv

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    executable = tmp_path / ("uv.exe" if sys.platform == "win32" else "uv")
    executable.write_bytes(b"synthetic verified uv control")
    (tmp_path / "uv-owner.json").write_text(
        json.dumps({"sha256": hashlib.sha256(executable.read_bytes()).hexdigest()})
    )
    assert installer_uv() == str(executable)


@pytest.mark.parametrize(
    "version,expected", [("14.7", False), ("15.0", True), ("26.0", True), ("", False)]
)
def test_pinned_mlx_wheel_os_floor_is_reported_before_install(
    version: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(runtime.platform, "mac_ver", lambda: (version, (), "arm64"))
    assert runtime.supported() is expected
