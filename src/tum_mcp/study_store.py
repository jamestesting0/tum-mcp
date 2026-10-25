"""Confined local paths and reversible writes for course study projects."""

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_models import StudyState
from tum_moodle.config import private_write

START = "<!-- tum-mcp:study:start -->"
END = "<!-- tum-mcp:study:end -->"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def confined(root: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or "\\" in relative or ":" in relative:
        raise CampusError(Code.WORKSPACE_CONFLICT, "A study path leaves the project.")
    current = root
    for part in name.parts:
        current /= part
        if current.is_symlink() or current.is_junction():
            raise CampusError(Code.WORKSPACE_CONFLICT, "Symbolic study paths were preserved.")
    return current


def read_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise CampusError(Code.WORKSPACE_CONFLICT, "A study file path is occupied.")
    return path.read_bytes()


def load_state(root: Path) -> StudyState:
    path = confined(root, ".study/state.json")
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise CampusError(Code.ACTION_REQUIRED, "Initialize one course with study init first.")
    try:
        return StudyState.model_validate_json(path.read_bytes())
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid study state; preserve and review it."
        ) from None


@dataclass(frozen=True, slots=True)
class Write:
    relative: str
    before: bytes | None
    after: bytes


def apply(root: Path, writes: tuple[Write, ...]) -> None:
    paths = [(item, confined(root, item.relative)) for item in writes]
    for item, path in paths:
        if read_bytes(path) != item.before:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Study files changed; inspect and retry.")
    applied: list[tuple[Write, Path]] = []
    try:
        for item, path in paths:
            if item.before == item.after:
                continue
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            private_write(path, item.after)
            applied.append((item, path))
    except OSError:
        restored = True
        for item, path in reversed(applied):
            try:
                if read_bytes(path) != item.after:
                    restored = False
                elif item.before is None:
                    path.unlink()
                else:
                    private_write(path, item.before)
            except OSError:
                restored = False
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Study update failed; previous files were restored."
            if restored
            else "Study update was interrupted; some files need local review.",
        ) from None


def replace_agents(existing: str, block: str, previous: StudyState | None) -> str:
    if START not in existing and END not in existing:
        if previous is not None:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Managed study instructions were removed.")
        return existing.rstrip() + ("\n\n" if existing else "") + block + "\n"
    if existing.count(START) != 1 or existing.count(END) != 1:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Study instruction markers need local review.")
    start, end = existing.index(START), existing.index(END) + len(END)
    old = existing[start:end]
    if end < start or previous is None or digest(old.encode()) != previous.agents_block_sha256:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Edited study inventory instructions were preserved."
        )
    return existing[:start] + block + existing[end:]
