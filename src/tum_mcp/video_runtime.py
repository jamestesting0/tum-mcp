"""Optional Video Notes render runtime: hash-locked, isolated and never part of base setup."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from filelock import FileLock, Timeout
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.installer_uv import installer_uv
from tum_mcp.settings import Frozen, data_dir

BUNDLE = Path(__file__).parent / "bundled" / "video_runtime"
SOURCE_BUILDS = frozenset({"pycairo", "manimpango", "srt"})
ENVIRONMENT = frozenset(
    {
        "HOME",
        "PATH",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "WINDIR",
        "LANG",
        "LC_ALL",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
    }
)
LINUX_PKGCONFIG = (
    "/usr/lib/x86_64-linux-gnu/pkgconfig",
    "/usr/lib/aarch64-linux-gnu/pkgconfig",
    "/usr/lib64/pkgconfig",
    "/usr/lib/pkgconfig",
    "/usr/share/pkgconfig",
    "/usr/local/lib/pkgconfig",
)


class RuntimeStatus(Frozen):
    supported: bool
    installed: bool
    profile: str
    reason: str
    missing: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()


def lock_path() -> Path:
    return BUNDLE / "requirements.lock"


def _code_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(BUNDLE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".lock":
            digest.update(path.relative_to(BUNDLE).as_posix().encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:12]


def _host() -> tuple[str, str]:
    machine = platform.machine().lower().replace("amd64", "x86_64").replace("arm64", "aarch64")
    return platform.system().lower(), machine


def profile() -> str:
    """Installed dependency identity; helper code runs from the package and is not part of it."""
    system, machine = _host()
    lock = hashlib.sha256(lock_path().read_bytes()).hexdigest()[:12]
    return f"manim-0.22.0-cp313-{system}-{machine}-{lock}"


def render_profile() -> str:
    return f"{profile()}-{_code_digest()}"


def runtime_root() -> Path:
    identity = profile()
    if platform.system() == "Windows":
        # Native DLL dependencies still hit MAX_PATH in otherwise long-path-aware Python.
        identity = "r-" + hashlib.sha256(identity.encode()).hexdigest()[:20]
    return data_dir() / "video-runtime" / identity


def executable_at(root: Path) -> Path:
    return root / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def python_path() -> Path:
    return executable_at(runtime_root())


def _mac_major() -> int:
    major = platform.mac_ver()[0].split(".", 1)[0]
    return int(major) if major.isdecimal() else 0


def supported() -> tuple[bool, str]:
    system, machine = _host()
    match system:
        case "windows":
            ok = machine == "x86_64"
            return ok, "" if ok else "Windows on ARM has no ManimPango wheel."
        case "darwin":
            ok = machine == "aarch64" and _mac_major() >= 14
            # Manim's OpenGL dependencies (moderngl, glcontext) publish no Intel macOS wheels.
            return ok, "" if ok else "Video rendering needs Apple Silicon with macOS 14+."
        case "linux":
            libc, version = platform.libc_ver()
            parts = version.split(".")[:2]
            ok = (
                machine == "x86_64"
                and libc == "glibc"
                and len(parts) == 2
                and all(part.isdecimal() for part in parts)
                and tuple(map(int, parts)) >= (2, 28)
            )
            # Linux ARM64 lacks the same OpenGL wheels.
            return ok, "" if ok else "Linux video rendering needs x86_64 with glibc 2.28+."
        case _:
            return False, "This operating system has no supported render runtime."


def _homebrew() -> Path | None:
    for candidate in (Path("/opt/homebrew"), Path("/usr/local")):
        if (candidate / "bin" / "brew").is_file():
            return candidate
    return None


def pkg_config_path() -> list[str]:
    system, _ = _host()
    if system == "darwin":
        brew = _homebrew()
        if brew is None:
            return []
        return [
            str(path)
            for path in (
                brew / "lib/pkgconfig",
                brew / "share/pkgconfig",
                brew / f"Library/Homebrew/os/mac/pkgconfig/{_mac_major()}",
            )
            if path.is_dir()
        ]
    if system == "linux":
        return [path for path in LINUX_PKGCONFIG if Path(path).is_dir()]
    return []


def prerequisites() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Missing native prerequisites and the exact commands the user can run."""
    system, _ = _host()
    folders = [Path(path) for path in pkg_config_path()]

    def has(name: str) -> bool:
        return any((folder / f"{name}.pc").is_file() for folder in folders)

    missing: list[str] = []
    commands: list[str] = []
    if system == "darwin":
        if _homebrew() is None:
            missing.append("Homebrew")
            commands.append("Install Homebrew from https://brew.sh, then: brew install cairo")
        elif not has("cairo"):
            missing.append("cairo")
            commands.append("brew install cairo")
        if not Path("/Library/Developer/CommandLineTools/usr/bin/clang").exists() and not (
            shutil.which("clang")
        ):
            missing.append("Xcode Command Line Tools")
            commands.append("xcode-select --install")
    elif system == "linux":
        packages = []
        if not has("cairo"):
            packages.append("libcairo2-dev")
        if not has("pangocairo"):
            packages.append("libpango1.0-dev")
        if not (shutil.which("cc") or shutil.which("gcc")):
            packages.append("build-essential")
        if packages:
            missing.extend(packages)
            commands.append("sudo apt install " + " ".join(packages))
            commands.append("(Fedora: sudo dnf install gcc cairo-devel pango-devel)")
    return tuple(missing), tuple(commands)


def summary() -> str:
    """Doctor detail from file checks only; never starts the runtime."""
    ok, why = supported()
    if not ok:
        return why
    missing, commands = prerequisites()
    if missing:
        return "Render prerequisites needed: " + "; ".join(commands)
    if python_path().is_file():
        return "Render runtime present; tum-mcp video-notes runtime status verifies it."
    return "Render runtime installs on first use (about 320 MB)."


def expected_versions() -> dict[str, str]:
    environment = {"python_version": "3.13", "python_full_version": "3.13.0"}
    result: dict[str, str] = {}
    for line in lock_path().read_text(encoding="utf-8").splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        requirement = Requirement(line.rstrip(" \\"))
        marker = requirement.marker
        if marker is None or Marker(str(marker)).evaluate(environment):
            result[canonicalize_name(requirement.name)] = next(iter(requirement.specifier)).version
    return result


def _environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key.upper() in ENVIRONMENT}
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    environment.update(extra or {})
    return environment


def _run(argv: tuple[str, ...], *, timeout: int, environment: dict[str, str]) -> str:
    try:
        # Fixed executables and validated paths, without a shell or campus state.
        completed = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            timeout=timeout,
            env=environment,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "The video runtime installer stopped or timed out."
        ) from None
    if completed.returncode:
        tail = completed.stderr.decode("utf-8", "replace").strip().splitlines()[-8:]
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Video runtime installation failed:\n" + "\n".join(tail),
        )
    return completed.stdout.decode("utf-8", "replace")


def _versions(executable: Path) -> dict[str, str]:
    code = (
        "import importlib.metadata as m,json;"
        "print(json.dumps({d.metadata['Name'].lower().replace('_','-'):"
        "d.version for d in m.distributions()}))"
    )
    try:
        value = json.loads(
            _run((str(executable), "-I", "-c", code), timeout=60, environment=_environment())
        )
    except (ValueError, CampusError):
        return {}
    return value if isinstance(value, dict) else {}


def status() -> RuntimeStatus:
    ok, why = supported()
    missing, commands = prerequisites() if ok else ((), ())
    installed = False
    if ok and python_path().is_file():
        versions = _versions(python_path())
        installed = bool(versions) and all(
            versions.get(name) == version for name, version in expected_versions().items()
        )
    reason = (
        "ready"
        if installed
        else why or ("prerequisites_missing" if missing else "runtime_not_installed")
    )
    return RuntimeStatus(
        supported=ok,
        installed=installed,
        profile=profile(),
        reason=reason,
        missing=missing,
        commands=commands,
    )


def install() -> RuntimeStatus:
    current = status()
    if not current.supported:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, current.reason)
    if current.installed:
        return current
    if current.missing:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Install the render prerequisites first, then retry: " + "; ".join(current.commands),
        )
    uv = installer_uv()
    if not uv:
        raise CampusError(Code.ACTION_REQUIRED, "Install uv before the optional video runtime.")
    destination = runtime_root()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with FileLock(str(destination) + ".lock", timeout=1):
            if status().installed:
                return status()
            if destination.exists():
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    f"An incomplete video runtime was preserved at {destination}; remove it "
                    "before retrying.",
                )
            with tempfile.TemporaryDirectory(prefix="video-", dir=destination.parent) as folder:
                candidate = Path(folder) / "runtime"
                _install_into(uv, candidate, Path(folder))
                candidate.rename(destination)
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Another process is installing the video runtime."
        ) from None
    return status()


def _install_into(uv: str, candidate: Path, scratch: Path) -> None:
    base = _environment()
    _run(
        (uv, "--no-config", "venv", "--python", "3.13", "--relocatable", str(candidate)),
        timeout=300,
        environment=base,
    )
    executable = executable_at(candidate)
    lock = lock_path().read_text(encoding="utf-8")
    blocks = lock.split("\n")
    first = next(i for i, line in enumerate(blocks) if line.startswith("pkgconf=="))
    end = next(
        (i for i in range(first + 1, len(blocks)) if blocks[i] and not blocks[i][0].isspace()),
        len(blocks),
    )
    phase_one = scratch / "pkgconf.lock"
    phase_one.write_text("\n".join(blocks[first:end]) + "\n", encoding="utf-8")
    sync = (uv, "--no-config", "pip", "sync", "--python", str(executable), "--require-hashes")
    index = ("--default-index", "https://pypi.org/simple")
    _run((*sync, "--only-binary", ":all:", *index, str(phase_one)), timeout=600, environment=base)
    names = sorted(
        canonicalize_name(Requirement(line.rstrip(" \\")).name)
        for line in blocks
        if line and not line[0].isspace() and not line.startswith("#")
    )
    binary = ",".join(name for name in names if name not in SOURCE_BUILDS)
    folder = "Scripts" if platform.system() == "Windows" else "bin"
    suffix = ".exe" if platform.system() == "Windows" else ""
    builder = {
        "PKG_CONFIG": str(candidate / folder / f"pkg-config{suffix}"),
        "PKG_CONFIG_PATH": os.pathsep.join(pkg_config_path()),
    }
    _run(
        (*sync, "--only-binary", binary, *index, str(lock_path())),
        timeout=1800,
        environment=_environment(builder),
    )
    versions = _versions(executable)
    if any(versions.get(name) != version for name, version in expected_versions().items()):
        raise CampusError(
            Code.INVALID_RESPONSE, "Installed video dependencies differ from their lock."
        )
    result = call_worker({"action": "health"}, executable=executable, timeout=300)
    if not result.get("ok") or not all(result.get("encoders", {}).values()):
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "The video runtime installed but failed its render health check.",
        )


def call_worker(
    request: dict,
    *,
    executable: Path | None = None,
    timeout: int = 3600,
    log: Path | None = None,
) -> dict:
    python = executable or python_path()
    if executable is None and not status().installed:
        raise CampusError(
            Code.ACTION_REQUIRED, "Install the render runtime: tum-mcp video-notes runtime install"
        )
    try:
        # Fixed runtime interpreter and bundled worker; only validated request data is passed.
        completed = subprocess.run(  # noqa: S603
            (str(python), "-I", str(BUNDLE / "worker.py")),
            input=json.dumps(request).encode(),
            capture_output=True,
            timeout=timeout,
            env=_environment(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise CampusError(
            Code.PENDING, f"The video worker exceeded its {timeout}s budget; work is resumable."
        ) from None
    except OSError:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "The video worker could not start."
        ) from None
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(completed.stderr[-200_000:])
    try:
        result = json.loads(completed.stdout[: 16 * 1024 * 1024])
    except ValueError:
        detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "The video worker crashed: " + " | ".join(detail),
        ) from None
    if not isinstance(result, dict):
        raise CampusError(Code.INVALID_RESPONSE, "The video worker returned an invalid result.")
    return result
