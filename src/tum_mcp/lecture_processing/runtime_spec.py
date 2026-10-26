"""Wheel-backed recognizer selection; no optional library imports or downloads."""

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from tum_mcp.lecture_processing.runtime_process import worker_path


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


def mac_major() -> int:
    major = platform.mac_ver()[0].split(".", 1)[0]
    return int(major) if major.isdecimal() else 0


def selected() -> RuntimeSpec:
    preference = os.environ.get("TUM_MCP_LECTURE_ENGINE", "auto")
    accelerated = (
        platform.system() == "Darwin" and platform.machine() == "arm64" and mac_major() >= 15
    )
    return MLX if preference == "mlx" or (preference == "auto" and accelerated) else CPU


def supported() -> bool:
    preference = os.environ.get("TUM_MCP_LECTURE_ENGINE", "auto")
    if preference not in {"auto", "cpu", "mlx"}:
        return False
    system, machine = platform.system(), platform.machine().lower()
    if selected() == MLX:
        return system == "Darwin" and machine == "arm64" and mac_major() >= 15
    match system:
        case "Windows":
            return machine in {"amd64", "x86_64"}
        case "Darwin":
            return mac_major() >= (14 if machine == "arm64" else 13) and machine in {
                "arm64",
                "x86_64",
            }
        case "Linux":
            libc, version = platform.libc_ver()
            parts = version.split(".")[:2]
            return (
                machine in {"x86_64", "aarch64", "arm64"}
                and libc == "glibc"
                and len(parts) == 2
                and all(p.isdecimal() for p in parts)
                and tuple(map(int, parts)) >= (2, 28)
            )
        case _:
            return False


def lock_path() -> Path:
    return worker_path().with_name(selected().lock)
