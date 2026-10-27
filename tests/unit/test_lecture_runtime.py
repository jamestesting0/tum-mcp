import json
import os
import sys
import types
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
    "system,machine,mac,libc,gpus,engine",
    [
        ("Windows", "AMD64", "", ("", ""), 0, "cpu"),
        ("Windows", "AMD64", "", ("", ""), 1, "cuda"),
        ("Linux", "x86_64", "", ("glibc", "2.28"), 0, "cpu"),
        ("Linux", "x86_64", "", ("glibc", "2.28"), 2, "cuda"),
        # CTranslate2's Linux ARM64 and macOS wheels have no CUDA build.
        ("Linux", "aarch64", "", ("glibc", "2.39"), 1, "cpu"),
        ("Darwin", "x86_64", "13.0", ("", ""), 1, "cpu"),
        ("Darwin", "arm64", "14.0", ("", ""), 0, "cpu"),
        ("Darwin", "arm64", "15.0", ("", ""), 0, "mlx"),
    ],
)
def test_native_backend_selection(system, machine, mac, libc, gpus, engine, tmp_path, monkeypatch):
    from tum_mcp.lecture_processing import runtime_spec
    from tum_mcp.lecture_processing.runtime_spec import selected

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runtime_spec, "nvidia_devices", lambda: gpus)
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


def test_windows_native_libraries_fit_nested_data_directory(monkeypatch):
    from pathlib import PureWindowsPath

    root = PureWindowsPath(
        "C:/Users/runneradmin/AppData/Local/Temp/pytest-of-runneradmin/pytest-0/"
        "test_real_pinned_recognition_a0/runtime-data"
    )
    monkeypatch.setattr(runtime, "data_dir", lambda: root)
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")
    library = runtime.runtime_root() / (
        "Lib/site-packages/av.libs/libopencore-amrnb-0-19c543506f45e59e9cc363b967322e5e.dll"
    )
    assert len(str(library)) < 260


def gpu_linux_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, gpus: int = 1) -> None:
    from tum_mcp.lecture_processing import runtime_spec

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(runtime.platform, "libc_ver", lambda: ("glibc", "2.35"))
    monkeypatch.setattr(runtime_spec, "nvidia_devices", lambda: gpus)


class FakeInstaller:
    """Stands in for uv and the worker; records locks synced and health environments."""

    def __init__(self, fail_health: set[str] = frozenset(), fail_sync: set[str] = frozenset()):
        self.fail_health, self.fail_sync = fail_health, fail_sync
        self.synced: list[str] = []
        self.health: list[tuple[str, dict]] = []

    def __call__(self, argv, payload=b"", timeout=1200, extra=None):
        if "venv" in argv:
            executable = runtime.executable_at(Path(argv[-1]))
            executable.parent.mkdir(parents=True)
            executable.write_text("synthetic")
            return b""
        if "sync" in argv:
            self.synced.append(Path(argv[-1]).name)
            if Path(argv[-1]).name in self.fail_sync:
                raise CampusError(runtime.Code.OFFLINE, "Synthetic offline")
            return b""
        if "-c" in argv:
            return json.dumps(runtime.expected_versions()).encode()
        backend = json.loads(payload)["backend"]
        self.health.append((backend, extra or {}))
        if backend in self.fail_health:
            raise CampusError(runtime.Code.CAPABILITY_UNSUPPORTED, "Synthetic GPU failure")
        return b'{"ready": true}'


def test_failed_gpu_keeps_automatic_selection_on_cpu_until_cuda_is_explicit(tmp_path, monkeypatch):
    from tum_mcp.lecture_processing.runtime_spec import cuda_declined_path, selected

    gpu_linux_host(monkeypatch, tmp_path)
    monkeypatch.delenv("TUM_MCP_LECTURE_ENGINE", raising=False)
    assert selected().backend == "cuda" and runtime.supported()
    cuda_declined_path().parent.mkdir(parents=True)
    cuda_declined_path().write_text("{}")
    assert selected().backend == "cpu"
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cuda")
    assert selected().backend == "cuda" and runtime.supported()
    monkeypatch.setattr(runtime.platform, "machine", lambda: "aarch64")
    assert not runtime.supported()


def test_unusable_gpu_installs_cpu_once_and_remembers_it(tmp_path, monkeypatch):
    from tum_mcp.lecture_processing.runtime_spec import cuda_declined_path

    gpu_linux_host(monkeypatch, tmp_path)
    monkeypatch.delenv("TUM_MCP_LECTURE_ENGINE", raising=False)
    monkeypatch.setattr(runtime, "installer_uv", lambda: "uv")
    fake = FakeInstaller(fail_health={"cuda"})
    monkeypatch.setattr(runtime, "isolated_run", fake)
    result = runtime.install()
    assert result.installed and result.engine == "cpu" and result.cuda_declined
    assert fake.synced == ["requirements-cuda.lock", "requirements-cpu.lock"]
    backend, environment = fake.health[0]
    assert backend == "cuda"
    assert Path(environment["LD_LIBRARY_PATH"]).parts[-6:] == (
        "lib",
        "python3.13",
        "site-packages",
        "nvidia",
        "cublas",
        "lib",
    )
    assert fake.health[1] == ("cpu", {})
    assert cuda_declined_path().is_file()
    fake.synced.clear()
    assert runtime.install().engine == "cpu" and fake.synced == []


def test_explicit_cuda_reports_failure_and_offline_installs_are_not_a_gpu_verdict(
    tmp_path, monkeypatch
):
    from tum_mcp.lecture_processing.runtime_spec import cuda_declined_path

    gpu_linux_host(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime, "installer_uv", lambda: "uv")
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cuda")
    monkeypatch.setattr(runtime, "isolated_run", FakeInstaller(fail_health={"cuda"}))
    with pytest.raises(CampusError, match="TUM_MCP_LECTURE_ENGINE=cpu"):
        runtime.install()
    assert not cuda_declined_path().exists() and not runtime.runtime_root().exists()
    monkeypatch.delenv("TUM_MCP_LECTURE_ENGINE")
    monkeypatch.setattr(
        runtime, "isolated_run", FakeInstaller(fail_sync={"requirements-cuda.lock"})
    )
    with pytest.raises(CampusError, match="Synthetic offline"):
        runtime.install()
    assert not cuda_declined_path().exists()
    cuda_declined_path().parent.mkdir(parents=True, exist_ok=True)
    cuda_declined_path().write_text("{}")
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cuda")
    monkeypatch.setattr(runtime, "isolated_run", FakeInstaller())
    assert runtime.install().engine == "cuda"
    assert not cuda_declined_path().exists()


@pytest.mark.parametrize(
    "system,variable,tail",
    [
        ("Windows", "CUDA_PATH", ("Lib", "site-packages", "nvidia", "cublas")),
        (
            "Linux",
            "LD_LIBRARY_PATH",
            ("lib", "python3.13", "site-packages", "nvidia", "cublas", "lib"),
        ),
    ],
)
def test_cuda_worker_finds_the_runtime_cublas(system, variable, tail, tmp_path, monkeypatch):
    # nvidia-cublas-cu12 wheels hold nvidia/cublas/bin/cublas64_12.dll (CTranslate2 loads
    # it from %CUDA_PATH%\\bin) and nvidia/cublas/lib/libcublas.so.12 (dlopen by name).
    monkeypatch.setattr(runtime.platform, "system", lambda: system)
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cuda")
    environment = runtime.worker_environment(tmp_path)
    assert list(environment) == [variable]
    assert Path(environment[variable]).parts[-len(tail) :] == tail
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cpu")
    assert runtime.worker_environment(tmp_path) == {}


def test_worker_library_paths_are_explicit_and_user_values_do_not_leak(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "user-library-path")
    code = "import os;print(os.environ.get('LD_LIBRARY_PATH','absent'))"
    assert isolated_run((sys.executable, "-I", "-c", code)).strip() == b"absent"
    extra = {"LD_LIBRARY_PATH": "runtime-cublas"}
    assert (
        isolated_run((sys.executable, "-I", "-c", code), extra=extra).strip() == b"runtime-cublas"
    )


def test_cuda_lock_is_the_cpu_lock_plus_pinned_cublas(monkeypatch):
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cpu")
    cpu = runtime.expected_versions()
    cpu_identity = (runtime.profile(), runtime.recognition_profile())
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cuda")
    cuda = runtime.expected_versions()
    added = {name: version for name, version in cuda.items() if cpu.get(name) != version}
    host_has_wheel = sys.platform in {"linux", "win32"}
    assert added == ({"nvidia-cublas-cu12": "12.8.4.1"} if host_has_wheel else {})
    assert set(cpu) <= set(cuda)
    # Separate runtime and chunk caches, so GPU and CPU transcripts are never mixed.
    assert runtime.profile() != cpu_identity[0]
    assert runtime.recognition_profile() != cpu_identity[1]


def test_ctranslate2_backends_share_decoding_and_cpu_settings_are_unchanged(monkeypatch):
    from tum_mcp.bundled.lecture_runtime import worker

    created: list[dict] = []

    class Model:
        def __init__(self, path: str, **settings) -> None:
            created.append(settings)

        def transcribe(self, audio, **options):
            created.append(options)
            return iter(()), types.SimpleNamespace(language="en")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    for backend in ("cpu", "cuda"):
        result = worker.recognize_ctranslate2(Path("model"), [], {}, backend)
        assert result == {"language": "en", "segments": []}
    cpu, cpu_options, cuda, cuda_options = created
    assert cpu == {
        "local_files_only": True,
        "num_workers": 1,
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": min(4, os.cpu_count() or 1),
    }
    assert cuda == {
        "local_files_only": True,
        "num_workers": 1,
        "device": "cuda",
        "device_index": 0,
        "compute_type": "float16",
    }
    assert cpu_options == cuda_options == worker.decoding_options("cpu")


def test_cuda_health_rejects_hosts_ctranslate2_cannot_use(monkeypatch):
    from tum_mcp.bundled.lecture_runtime import worker

    fake = types.SimpleNamespace(get_cuda_device_count=lambda: 0)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "webrtcvad", types.SimpleNamespace(Vad=lambda level: None))
    with pytest.raises(ValueError, match="No CUDA 12 capable GPU"):
        worker.health("cuda")
    fake.get_cuda_device_count = lambda: 1
    fake.get_supported_compute_types = lambda device: {"float32", "int8"}
    with pytest.raises(ValueError, match="float16"):
        worker.health("cuda")


def test_driver_probe_runs_and_reports_a_count_without_a_cuda_toolkit():
    from tum_mcp.lecture_processing import runtime_spec

    output = isolated_run((sys.executable, "-I", "-c", runtime_spec._DRIVER_PROBE), timeout=30)
    assert output.strip().isdigit()
