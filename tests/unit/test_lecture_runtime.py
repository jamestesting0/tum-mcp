import sys
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.lecture_processing import runtime
from tum_mcp.lecture_processing.runtime_process import isolated_run


@pytest.mark.parametrize(
    "system,machine", [("Windows", "ARM64"), ("Linux", "i686"), ("FreeBSD", "amd64")]
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
    assert isolated_run(
        (
            sys.executable,
            "-I",
            "-c",
            "import os;print(os.environ.get('CAMPUS_COOKIE','absent'))",
        )
    ).splitlines() == [b"absent"]


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
    "version,expected",
    [("13.7", False), ("14.0", True), ("15.0", True), ("26.0", True), ("", False)],
)
def test_pinned_mlx_wheel_os_floor_is_reported_before_install(
    version: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(runtime.platform, "mac_ver", lambda: (version, (), "arm64"))
    assert runtime.supported() is expected


def test_decoding_settings_invalidate_inference_without_reinstalling_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency_profile = runtime.profile()
    before = runtime.recognition_profile()
    current = runtime.decoding_options()
    monkeypatch.setattr(
        runtime, "decoding_options", lambda backend: {**current, "temperature": 0.1}
    )
    assert runtime.recognition_profile() != before
    assert runtime.profile() == dependency_profile


@pytest.mark.parametrize(
    "system,machine,mac,libc,engine",
    [
        ("Windows", "AMD64", "", ("", ""), "cpu"),
        ("Linux", "x86_64", "", ("glibc", "2.28"), "cpu"),
        ("Linux", "aarch64", "", ("glibc", "2.39"), "cpu"),
        ("Darwin", "x86_64", "13.0", ("", ""), "cpu"),
        ("Darwin", "arm64", "14.0", ("", ""), "cpu"),
        ("Darwin", "arm64", "15.0", ("", ""), "mlx"),
    ],
)
def test_native_backend_selection(system, machine, mac, libc, engine, monkeypatch):
    from tum_mcp.lecture_processing.runtime_spec import selected

    monkeypatch.delenv("TUM_MCP_LECTURE_ENGINE", raising=False)
    monkeypatch.setattr(runtime.platform, "system", lambda: system)
    monkeypatch.setattr(runtime.platform, "machine", lambda: machine)
    monkeypatch.setattr(runtime.platform, "mac_ver", lambda: (mac, (), machine))
    monkeypatch.setattr(runtime.platform, "libc_ver", lambda: libc)
    assert runtime.supported()
    assert selected().backend == engine
    if system == "Windows":
        assert runtime.python_path().parts[-2:] == ("Scripts", "python.exe")


def test_cpu_lock_markers_match_host_instead_of_requiring_other_platforms(monkeypatch):
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cpu")
    versions = runtime.expected_versions()
    assert versions["faster-whisper"] == "1.2.1"
    assert "mlx" not in versions and "httpx2-jsfetch" not in versions
    assert ("colorama" in versions) == (sys.platform == "win32")
    assert ("pyreadline3" in versions) == (sys.platform == "win32")


def test_cpu_override_and_unsupported_settings_fail_honestly(monkeypatch):
    from tum_mcp.lecture_processing.runtime_spec import selected

    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(runtime.platform, "mac_ver", lambda: ("15.0", (), "arm64"))
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cpu")
    assert runtime.supported() and selected().backend == "cpu"
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "arbitrary-import")
    assert not runtime.supported()


def test_worker_preserves_windows_home_and_temp_without_hub_credentials(monkeypatch):
    import json

    monkeypatch.setenv("USERPROFILE", "synthetic-home")
    monkeypatch.setenv("TEMP", "synthetic-temp")
    monkeypatch.setenv("HF_TOKEN", "synthetic-secret")
    code = (
        "import os,json;"
        "print(json.dumps([os.getenv(k) for k in ('USERPROFILE','TEMP','HF_TOKEN')]))"
    )
    assert json.loads(isolated_run((sys.executable, "-I", "-c", code))) == [
        "synthetic-home",
        "synthetic-temp",
        None,
    ]


@pytest.mark.parametrize("libc", [("musl", "1.2.5"), ("glibc", "2.27"), ("", "")])
def test_linux_without_required_glibc_wheels_is_reported_unsupported(libc, monkeypatch):
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cpu")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(runtime.platform, "libc_ver", lambda: libc)
    assert not runtime.supported()


def test_model_request_without_runtime_does_not_block_later_install(tmp_path, monkeypatch):
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    with pytest.raises(CampusError, match="Install the optional lecture runtime"):
        runtime.model("base")
    assert not runtime.runtime_root().exists()


def test_invalid_model_receipt_is_preserved_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    executable = runtime.python_path()
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"synthetic-runtime")
    receipt = runtime.runtime_root() / "model-base.json"
    receipt.write_text("invalid edited receipt")
    monkeypatch.setattr(runtime, "call_worker", lambda *a, **kw: pytest.fail("No download"))
    with pytest.raises(CampusError, match="receipt is invalid"):
        runtime.model("base")
    assert receipt.read_text() == "invalid edited receipt"
