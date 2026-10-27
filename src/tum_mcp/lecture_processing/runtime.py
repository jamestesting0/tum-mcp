"""Explicit wheel-only local recognition runtime, independent of base installation."""

import hashlib
import json
import platform
import shutil
import tempfile
from pathlib import Path

from filelock import FileLock, Timeout
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tum_mcp.bundled.lecture_runtime.worker import decoding_options
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.installer_uv import installer_uv
from tum_mcp.lecture_processing.runtime_assets import ModelAsset, model  # noqa: F401
from tum_mcp.lecture_processing.runtime_process import isolated_run, worker_path
from tum_mcp.lecture_processing.runtime_spec import lock_path, selected, supported  # noqa: F401
from tum_mcp.settings import Frozen, data_dir


class RuntimeStatus(Frozen):
    supported: bool
    installed: bool
    ffmpeg: bool
    profile: str
    reason: str
    models: tuple[str, ...] = ()
    engine: str = ""


def profile() -> str:
    digest = hashlib.sha256(lock_path().read_bytes()).hexdigest()[:16]
    machine = platform.machine().lower().replace("amd64", "x86_64")
    system = platform.system().lower()
    return f"{selected().engine}-cp313-{system}-{machine}-{digest}"


def recognition_profile() -> str:
    """Decoder changes invalidate inference without reinstalling identical dependencies."""
    options = hashlib.sha256(
        json.dumps(decoding_options(selected().backend), sort_keys=True).encode()
    ).hexdigest()[:16]
    return f"{profile()}-decode-{options}"


def runtime_root() -> Path:
    identity = profile()
    if platform.system() == "Windows":
        # Native DLL dependencies still hit MAX_PATH in otherwise long-path-aware Python.
        identity = "r-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    return data_dir() / "lecture-runtime" / identity


def python_path() -> Path:
    return executable_at(runtime_root())


def executable_at(root: Path) -> Path:
    return root / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def expected_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lock_path().read_text().splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        requirement = Requirement(line.rstrip(" \\"))
        if requirement.marker is None or requirement.marker.evaluate({"python_version": "3.13"}):
            result[canonicalize_name(requirement.name)] = next(iter(requirement.specifier)).version
    return result


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
            for name, (_, revision) in selected().models.items():
                receipt = runtime_root() / f"model-{name}.json"
                if receipt.is_file():
                    from tum_mcp.lecture_processing.runtime_assets import read_asset

                    asset = read_asset(receipt)
                    if asset is not None and asset.revision == revision:
                        models.append(name)
    return RuntimeStatus(
        supported=supported(),
        installed=installed,
        ffmpeg=bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        profile=profile(),
        reason="ready"
        if installed
        else "runtime_not_installed"
        if supported()
        else "automatic_asr_host_or_engine_unsupported",
        models=tuple(models),
        engine=selected().backend,
    )


def install() -> RuntimeStatus:
    if not supported():
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Automatic ASR has no locked wheels for this host or selected engine. "
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
                    (
                        uv,
                        "--no-config",
                        "venv",
                        "--python",
                        "3.13",
                        "--relocatable",
                        str(candidate),
                    ),
                    timeout=300,
                )
                executable = executable_at(candidate)
                isolated_run(
                    (
                        uv,
                        "--no-config",
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
                isolated_run(
                    (str(executable), "-I", str(worker_path())),
                    json.dumps({"action": "health", "backend": selected().backend}).encode(),
                    timeout=60,
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
    payload = json.dumps({"action": action, "backend": selected().backend, **arguments}).encode()
    return isolated_run((str(python_path()), "-I", str(worker_path())), payload)
