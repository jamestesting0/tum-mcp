"""Explicit wheel-only Apple Silicon runtime, independent of base installation."""

import hashlib
import json
import platform
import re
import shutil
import tempfile
from pathlib import Path

from filelock import FileLock, Timeout
from pydantic import Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.installer_uv import installer_uv
from tum_mcp.lecture_processing.runtime_process import isolated_run, worker_path
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen, data_dir

ENGINE = "mlx-whisper-0.4.3"
MODELS = {
    "base": ("mlx-community/whisper-base-mlx", "1e3e249fb8d01c655324bd6841b1deadffd6d04c"),
    "small.en": ("mlx-community/whisper-small.en-mlx", "52a88bf6e98b114a210c21bb83e22d6e1505cb73"),
}


class RuntimeStatus(Frozen):
    supported: bool
    installed: bool
    ffmpeg: bool
    profile: str
    reason: str
    models: tuple[str, ...] = ()


class ModelAsset(Frozen):
    path: Path
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    weights_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def supported() -> bool:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return False
    major = platform.mac_ver()[0].split(".", 1)[0]
    # The separately locked MLX/Metal wheels target macOS 15; no source build fallback.
    return major.isdecimal() and int(major) >= 15


def lock_path() -> Path:
    return worker_path().with_name("requirements.lock")


def profile() -> str:
    digest = hashlib.sha256(lock_path().read_bytes()).hexdigest()[:16]
    return f"{ENGINE}-cp313-darwin-arm64-{digest}"


def runtime_root() -> Path:
    return data_dir() / "lecture-runtime" / profile()


def python_path() -> Path:
    return runtime_root() / "bin/python"


def expected_versions() -> dict[str, str]:
    return dict(re.findall(r"^([a-zA-Z0-9_-]+)==([^\s;\\]+)", lock_path().read_text(), re.M))


def _versions(executable: Path) -> dict[str, str]:
    code = (
        "import importlib.metadata as m,json;"
        "print(json.dumps({d.metadata['Name'].lower().replace('_','-'):"
        "d.version for d in m.distributions()}))"
    )
    try:
        result = json.loads(isolated_run((str(executable), "-I", "-c", code), timeout=30))
        if isinstance(result, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in result.items()
        ):
            return result
    except (ValueError, CampusError):
        pass
    return {}


def status() -> RuntimeStatus:
    installed = False
    models: list[str] = []
    if supported() and python_path().is_file():
        versions = _versions(python_path())
        installed = all(versions.get(k) == v for k, v in expected_versions().items())
        if installed:
            for name in MODELS:
                receipt = runtime_root() / f"model-{name}.json"
                if receipt.is_file():
                    try:
                        asset = ModelAsset.model_validate_json(receipt.read_bytes())
                        if (
                            asset.revision == MODELS[name][1]
                            and (asset.path / "weights.npz").is_file()
                        ):
                            models.append(name)
                    except ValidationError:
                        pass
    return RuntimeStatus(
        supported=supported(),
        installed=installed,
        ffmpeg=bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        profile=profile(),
        reason="ready"
        if installed
        else "runtime_not_installed"
        if supported()
        else "automatic_asr_requires_native_apple_silicon_macos_15_or_later",
        models=tuple(models),
    )


def install() -> RuntimeStatus:
    if not supported():
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Automatic ASR requires native Apple Silicon macOS 15+. "
            "Timed captions remain supported.",
        )
    uv = installer_uv()
    if not uv:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Install uv before explicitly installing the optional lecture runtime.",
        )
    destination = runtime_root()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with FileLock(str(destination) + ".lock", timeout=1):
            if status().installed:
                return status()
            if destination.exists():
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    "Existing incomplete runtime preserved; remove that runtime directory "
                    "before retrying.",
                )
            with tempfile.TemporaryDirectory(
                prefix="lecture-install-", dir=destination.parent
            ) as folder:
                candidate = Path(folder) / "runtime"
                isolated_run(
                    (uv, "venv", "--python", "3.13", "--relocatable", str(candidate)), timeout=300
                )
                executable = candidate / "bin/python"
                isolated_run(
                    (
                        uv,
                        "pip",
                        "sync",
                        "--python",
                        str(executable),
                        "--require-hashes",
                        "--only-binary",
                        ":all:",
                        "--default-index",
                        "https://pypi.org/simple",
                        str(lock_path()),
                    ),
                    timeout=1200,
                )
                versions = _versions(executable)
                if any(versions.get(k) != v for k, v in expected_versions().items()):
                    raise CampusError(
                        Code.INVALID_RESPONSE,
                        "Installed lecture dependency versions differ from their lock.",
                    )
                candidate.rename(destination)
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Another process is installing the lecture runtime."
        ) from None
    return status()


def call_worker(action: str, **arguments: str | int) -> bytes:
    if not status().installed:
        raise CampusError(
            Code.ACTION_REQUIRED, "Run tum-mcp lecture runtime install, or supply timed captions."
        )
    payload = json.dumps({"action": action, **arguments}).encode()
    return isolated_run((str(python_path()), "-I", str(worker_path())), payload)


def model(name: str) -> ModelAsset:
    if name not in MODELS:
        raise CampusError(Code.INVALID_RESPONSE, "Unknown pinned lecture model.")
    repo, revision = MODELS[name]
    root = runtime_root()
    with FileLock(str(root / "models.lock"), timeout=1200):
        receipt = root / f"model-{name}.json"
        if receipt.is_file():
            try:
                existing = ModelAsset.model_validate_json(receipt.read_bytes())
                if existing.revision == revision:
                    return existing
            except ValidationError:
                raise CampusError(
                    Code.INVALID_RESPONSE, "Pinned model receipt is invalid."
                ) from None
        asset = ModelAsset.model_validate_json(call_worker("model", repo=repo, revision=revision))
        if asset.revision != revision:
            raise CampusError(Code.INVALID_RESPONSE, "Pinned model revision could not be verified.")
        private_write(receipt, asset.model_dump_json().encode())
        return asset
