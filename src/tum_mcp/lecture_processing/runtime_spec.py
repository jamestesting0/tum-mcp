"""Wheel-backed recognizer selection; no optional library imports or downloads."""

import os
import platform
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tum_mcp.errors import CampusError
from tum_mcp.lecture_processing.runtime_process import isolated_run, worker_path
from tum_mcp.settings import data_dir


@dataclass(frozen=True)
class RuntimeSpec:
    backend: str
    engine: str
    lock: str
    weights: str
    models: dict[str, tuple[str, str]]


MLX = RuntimeSpec(
    "mlx",
    "mlx-whisper-0.4.3",
    "requirements.lock",
    "weights.npz",
    {
        "base": ("mlx-community/whisper-base-mlx", "1e3e249fb8d01c655324bd6841b1deadffd6d04c"),
        "small.en": (
            "mlx-community/whisper-small.en-mlx",
            "52a88bf6e98b114a210c21bb83e22d6e1505cb73",
        ),
    },
)
CPU = RuntimeSpec(
    "cpu",
    "faster-whisper-1.2.1",
    "requirements-cpu.lock",
    "model.bin",
    {
        "base": ("Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"),
        "small.en": ("Systran/faster-whisper-small.en", "d1d751a5f8271d482d14ca55d9e2deeebbae577f"),
    },
)
# Same CTranslate2 models as CPU; the lock adds the cuBLAS its CUDA 12.8 build loads.
CUDA = RuntimeSpec(
    "cuda", "faster-whisper-1.2.1-cuda12", "requirements-cuda.lock", "model.bin", CPU.models
)
ENGINES = frozenset({"auto", "cpu", "mlx", "cuda"})
# Asks the NVIDIA driver itself, so no CUDA toolkit is needed. Driver API 12000 is
# CUDA 12.0; attribute 75 is the compute capability major. CTranslate2 offers float16
# only from 7.0 (Volta/Turing on), and the worker uses device 0.
_DRIVER_PROBE = """
import ctypes, sys
try:
    driver = ctypes.WinDLL("nvcuda.dll") if sys.platform == "win32" else ctypes.CDLL("libcuda.so.1")
    version, count, device, major = (ctypes.c_int() for _ in range(4))
    ready = (
        driver.cuInit(0) == 0
        and driver.cuDriverGetVersion(ctypes.byref(version)) == 0
        and driver.cuDeviceGetCount(ctypes.byref(count)) == 0
        and count.value > 0
        and driver.cuDeviceGet(ctypes.byref(device), 0) == 0
        and driver.cuDeviceGetAttribute(ctypes.byref(major), 75, device) == 0
    )
    print(count.value if ready and version.value >= 12000 and major.value >= 7 else 0)
except OSError:
    print(0)
"""


def mac_major() -> int:
    major = platform.mac_ver()[0].split(".", 1)[0]
    return int(major) if major.isdecimal() else 0


def _glibc_228() -> bool:
    libc, version = platform.libc_ver()
    parts = version.split(".")[:2]
    return (
        libc == "glibc"
        and len(parts) == 2
        and all(p.isdecimal() for p in parts)
        and tuple(map(int, parts)) >= (2, 28)
    )


def cuda_host() -> bool:
    """Hosts whose CTranslate2 wheel is built with CUDA (not Linux ARM64 or macOS)."""
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows":
        return machine in {"amd64", "x86_64"}
    return system == "Linux" and machine == "x86_64" and _glibc_228()


@cache
def nvidia_devices() -> int:
    """NVIDIA GPUs usable for float16 CUDA 12 recognition, probed once in a subprocess."""
    try:
        output = isolated_run((sys.executable, "-I", "-c", _DRIVER_PROBE), timeout=30)
        return int(output.strip() or 0)
    except (CampusError, ValueError):
        return 0


def cuda_declined_path() -> Path:
    return data_dir() / "lecture-runtime" / "cuda-unusable.json"


def selected() -> RuntimeSpec:
    preference = os.environ.get("TUM_MCP_LECTURE_ENGINE", "auto")
    if preference != "auto":
        # Unknown values stay on CPU here; supported() reports them as unsupported.
        return {"mlx": MLX, "cuda": CUDA}.get(preference, CPU)
    if platform.system() == "Darwin" and platform.machine() == "arm64" and mac_major() >= 15:
        return MLX
    if cuda_host() and not cuda_declined_path().exists() and nvidia_devices() > 0:
        return CUDA
    return CPU


def supported() -> bool:
    preference = os.environ.get("TUM_MCP_LECTURE_ENGINE", "auto")
    if preference not in ENGINES:
        return False
    system, machine = platform.system(), platform.machine().lower()
    if selected() == MLX:
        return system == "Darwin" and machine == "arm64" and mac_major() >= 15
    if selected() == CUDA:
        return cuda_host()
    match system:
        case "Windows":
            return machine in {"amd64", "x86_64"}
        case "Darwin":
            return mac_major() >= (14 if machine == "arm64" else 13) and machine in {
                "arm64",
                "x86_64",
            }
        case "Linux":
            return machine in {"x86_64", "aarch64", "arm64"} and _glibc_228()
        case _:
            return False


def lock_path() -> Path:
    return worker_path().with_name(selected().lock)
