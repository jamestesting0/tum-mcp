"""Explicit check that the CUDA runtime's pinned cuBLAS loads the way CTranslate2 loads it."""

import json
import os
import shutil
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.lecture_processing import runtime
from tum_mcp.lecture_processing.runtime_process import isolated_run, worker_path
from tum_mcp.lecture_processing.runtime_spec import cuda_host

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_LECTURE_CUDA_LIBRARIES") != "1" or not cuda_host(),
    reason="Downloads the CUDA runtime (about 600 MB); select it on Windows x64 or Linux x86_64.",
)

CHECK = """
import ctypes, json, sys
sys.path.insert(0, sys.argv[1])
import ctranslate2, worker
major = ctypes.c_int()
status = worker.load_cublas().cublasGetProperty(0, ctypes.byref(major))
gpus = ctranslate2.get_cuda_device_count()
print(json.dumps({"status": status, "major": major.value, "gpus": gpus}))
"""


def test_cuda_runtime_loads_its_pinned_cublas_without_a_gpu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", "cuda")
    uv = shutil.which("uv")
    assert uv, "uv is required to install the runtime"
    root = tmp_path / "cuda-runtime"
    isolated_run((uv, "--no-config", "venv", "--python", "3.13", "--relocatable", str(root)))
    python = str(runtime.executable_at(root))
    isolated_run(
        (
            uv,
            "--no-config",
            "pip",
            "sync",
            "--python",
            python,
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--default-index",
            "https://pypi.org/simple",
            str(runtime.lock_path()),
        )
    )
    extra = runtime.worker_environment(root)
    checked = json.loads(
        isolated_run((python, "-I", "-c", CHECK, str(worker_path().parent)), extra=extra)
    )
    assert checked["status"] == 0 and checked["major"] == 12
    if checked["gpus"] == 0:
        # The real health check must fail cleanly so automatic selection falls back to CPU.
        health = json.dumps({"action": "health", "backend": "cuda"}).encode()
        with pytest.raises(CampusError, match="runtime failed"):
            isolated_run((python, "-I", str(worker_path())), health, timeout=60, extra=extra)
