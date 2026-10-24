"""Track managed MCP backends without inspecting unrelated applications or credentials."""

import json
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import data_dir, data_path
from tum_moodle.config import private_write


def removal_marker() -> Path:
    return data_path() / "runtime-removal.pending"


@contextmanager
def runtime_lease() -> Iterator[None]:
    python = Path(sys.executable)
    try:
        relative = python.parent.resolve().relative_to(data_path() / "runtimes")
        managed = bool(relative.parts and re.fullmatch(r"[a-f0-9]{64}", relative.parts[0]))
    except ValueError:
        managed = False
    if not managed:
        yield
        return
    root = data_dir()
    identifier = uuid4().hex
    directory = root / "runtime-leases"
    if directory.is_symlink():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Symbolic runtime lease directory preserved.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = directory / f"{identifier}.json"
    lease = FileLock(str(directory / f"{identifier}.lock"), timeout=0)
    with FileLock(str(root / "runtime-cleanup.lock")):
        if removal_marker().exists():
            raise CampusError(
                Code.ACTION_REQUIRED, "Runtime removal is pending; run setup to recover."
            )
        lease.acquire()
        private_write(record, json.dumps({"pid": os.getpid(), "python": str(python)}).encode())
    try:
        yield
    finally:
        record.unlink(missing_ok=True)
        lease.release()
        Path(lease.lock_file).unlink(missing_ok=True)


def require_idle_runtimes() -> None:
    directory = data_path() / "runtime-leases"
    if directory.is_symlink():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Symbolic runtime lease directory preserved.")
    for record in directory.glob("*.json"):
        if (
            not re.fullmatch(r"[a-f0-9]{32}\.json", record.name)
            or record.with_suffix(".lock").is_symlink()
        ):
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Unknown runtime lease files need local review."
            )
        lock = FileLock(str(record.with_suffix(".lock")), timeout=0)
        try:
            with lock:
                record.unlink(missing_ok=True)
        except Timeout:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "A TUM MCP client is still running. Close coding clients before runtime removal.",
            ) from None
