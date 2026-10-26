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
