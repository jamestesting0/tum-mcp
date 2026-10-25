"""Explicit removal of managed clients and optional local credential records."""

import hashlib
import re
from contextlib import ExitStack
from pathlib import Path

from filelock import FileLock

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browser_runtime import NODE_HASHES, NODE_VERSION
from tum_mcp.moodle.browsers import is_wsl, windows_host, wsl_path
from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.downloads import downloads_root
from tum_mcp.moodle.platforms import data_root
from tum_mcp.runtime_leases import removal_marker, require_idle_runtimes
from tum_mcp.settings import data_dir, data_path, preferences
from tum_mcp.uninstall import uninstall_client
from tum_mcp.updates import installation_targets


def remove_clients(*, purge_runtime: bool = False, forget_credentials: bool = False) -> int:
    removed = 0
    errors: list[str] = []
    with FileLock(str(data_dir() / "runtime-cleanup.lock")):
        if purge_runtime or forget_credentials:
            require_idle_runtimes()
        if purge_runtime:
            _protect_user_directories()
        targets, discovery = installation_targets()
        errors.extend(item.detail for item in discovery if item.state == "needs_review")
        for name, host, home in targets:
            try:
                removed += uninstall_client(name, home, host=host)
            except CampusError as error:
                errors.append(f"{name} ({host.value}): {error.message}")
            except OSError:
                errors.append(f"{name}: client files could not be accessed; preserved.")
        if errors:
            for error in errors:
                print(error)
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Some clients need review; runtimes and credentials were retained.",
            )
        if forget_credentials:
            _forget_local_credentials()
            print(
                "Local service credentials and Git tokens removed. "
                "Native-store records were retained."
            )
        if purge_runtime:
            _remove_windows_driver()
            private_write(removal_marker(), b"explicit-runtime-removal\n")
    print(f"Removed {removed} managed client registration(s).")
    print("User settings, custom files, downloads, course cache and assignment work were retained.")
    return removed


def _forget_local_credentials() -> None:
    root = data_path() / "credentials"
    local = root / "local"
    if root.is_symlink() or local.is_symlink():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Symbolic credential directory preserved.")
    moodle = data_root().expanduser().resolve() / "local-session"
    if moodle.is_symlink():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Symbolic Moodle session directory preserved.")
    if local.is_dir():
        records = tuple(sorted(local.glob("*.enc")))
        if any(not re.fullmatch(r"[a-f0-9]{64}\.enc", path.name) for path in records):
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Unknown credential files preserved for review."
            )
        with ExitStack() as leases:
            for record in records:
                leases.enter_context(FileLock(str(root / f"{record.stem}.lease.lock"), timeout=30))
            leases.enter_context(FileLock(str(root / "vault.lock")))
            if tuple(sorted(local.glob("*.enc"))) != records:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Credential records changed; close clients and retry."
                )
            for record in records:
                record.unlink()
            (local / "session.key").unlink(missing_ok=True)
    if moodle.is_dir():
        with FileLock(str(moodle / "session.lock")):
            for name in ("session.enc", "session.key", "login.json"):
                (moodle / name).unlink(missing_ok=True)
            # Invalidate a connection attempt that was started before logout.
            from uuid import uuid4

            private_write(moodle / "generation", uuid4().hex.encode())


def _remove_windows_driver() -> None:
    if not is_wsl():
        return
    host = windows_host()
    directory = (
        host.local_data / "TUMMCP" / "browser-runtime" / f"node-{NODE_VERSION}-{host.architecture}"
    )
    executable = Path(wsl_path(str(directory / "node.exe")))
    if not executable.exists():
        return
    if (
        executable.is_symlink()
        or hashlib.sha256(executable.read_bytes()).hexdigest() != NODE_HASHES[host.architecture][1]
    ):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Modified Windows browser runtime preserved for review."
        )
    executable.unlink()
    if not any(executable.parent.iterdir()):
        executable.parent.rmdir()


def _protect_user_directories() -> None:
    runtimes = (data_path() / "runtimes").resolve()
    protected = (
        preferences().workspace_root.expanduser().resolve(),
        downloads_root().expanduser().resolve(),
        data_root().expanduser().resolve(),
    )
    if any(path.is_relative_to(runtimes) or runtimes.is_relative_to(path) for path in protected):
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Runtime paths overlap user work, downloads or Moodle data; "
            "automatic cleanup was refused.",
        )
