"""The edit transaction around an Ask agent turn.

The server does not trust the agent alone: it snapshots the authored content before a turn,
reverts any change to protected files after it, gates the change on a local build and the
course's lint checks, and keeps the previous files so the student can undo the edit while
nothing changed since.
"""

import json
import shutil
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pydantic import ValidationError

from tum_mcp.course.project.paths import APP
from tum_mcp.course.project.store import (
    PRIVATE,
    Write,
    apply,
    confined,
    digest,
    private_path,
    read_bytes,
)
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write

AUTHORED = tuple(f"{APP}/{folder}" for folder in ("study", "exercises", "exam", "lectures"))
PROTECTED = ("AGENTS.md", f"{PRIVATE}/course.md", f"{PRIVATE}/state.json", f"{PRIVATE}/github.json")
KEEP = 20


@dataclass(slots=True)
class Snapshot:
    authored: dict[str, bytes] = field(default_factory=dict)
    protected: dict[str, bytes | None] = field(default_factory=dict)


def _authored(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for folder in AUTHORED:
        base = confined(root, folder)
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def snapshot(root: Path) -> Snapshot:
    return Snapshot(_authored(root), {name: read_bytes(confined(root, name)) for name in PROTECTED})


def changed(root: Path, before: Snapshot) -> dict[str, tuple[bytes | None, bytes | None]]:
    after = _authored(root)
    return {
        name: (before.authored.get(name), after.get(name))
        for name in sorted(set(before.authored) | set(after))
        if before.authored.get(name) != after.get(name)
    }


def revert_protected(root: Path, before: Snapshot) -> list[str]:
    reverted = []
    for name, body in before.protected.items():
        path = confined(root, name)
        if read_bytes(path) != body:
            if body is None:
                path.unlink(missing_ok=True)
            else:
                private_write(path, body)
            reverted.append(name)
    return reverted


def restore(root: Path, changes: dict[str, tuple[bytes | None, bytes | None]]) -> None:
    apply(root, tuple(Write(name, after, before) for name, (before, after) in changes.items()))


def _items(items: Iterable[str], names: Iterable[str]) -> list[str]:
    """The review items behind app files: same workspace, key ending in the file's name."""
    keys: list[str] = []
    for name in names:
        parts = PurePosixPath(name).parts
        if len(parts) < 3:
            continue
        stem = PurePosixPath(name).stem
        for key in items:
            if key.split("/")[0] == parts[1] and key.rsplit("/", 1)[-1] == stem and key not in keys:
                keys.append(key)
    return keys


def problems(root: Path, names: Iterable[str]) -> dict[str, dict[str, str]]:
    """The blocking lint problems of the items behind the named files, per item.

    Each problem is keyed by its flag and place rather than its wording, so a problem that was
    there before the edit is recognised after it even when the edited text changed.
    """
    from tum_mcp.course.cli import lint_item
    from tum_mcp.course.ledger.coverage import read_ledger
    from tum_mcp.course.review import loop
    from tum_mcp.course.review.models import COURSE_WIDE_FLAGS, INVARIANT_FLAGS

    ledger = read_ledger(root)
    outcomes = {o.key for s in ledger.sources for o in s.outcomes} if ledger else None
    found: dict[str, dict[str, str]] = {}
    for key in _items(loop.load(root).items, names):
        result = lint_item(root, loop.load(root, answer_item=key), key, outcomes)
        current = {
            f"{flag['flag']} at {flag['item']}": str(flag.get("detail", flag["flag"]))
            for flag in result["flags"]
            if flag["flag"] in INVARIANT_FLAGS and flag["flag"] not in COURSE_WIDE_FLAGS
        }
        current |= {problem: problem for problem in result["plan"]["problems"]}
        if (answer := result["answer_key"]) and not answer["passed"]:
            current["answer key"] = json.dumps(answer, ensure_ascii=False)[:500]
        found[key] = current
    return found


class Baseline:
    """The anchored item's lint problems before a turn, found while the agent works."""

    def __init__(self, root: Path, names: list[str]) -> None:
        self.root, self.names = root, names
        self.before: dict[str, dict[str, str]] | None = None
        self.seen: dict[str, bytes | None] = {}
        self.thread = threading.Thread(target=self._find, daemon=True)
        self.thread.start()

    def _read(self) -> dict[str, bytes | None]:
        return {name: read_bytes(confined(self.root, name)) for name in self.names}

    def _find(self) -> None:
        seen = self._read()
        try:
            found = problems(self.root, self.names)
        except (CampusError, ValidationError, OSError, ValueError):
            return
        # An edit that landed while this ran leaves no clean baseline; the gate redoes it.
        if self._read() == seen:
            self.before, self.seen = found, seen

    def _restored(
        self, changes: dict[str, tuple[bytes | None, bytes | None]], touched: set[str]
    ) -> dict[str, dict[str, str]] | None:
        """The problems of the files as they were before the turn, put back for the check."""
        try:
            for name in touched:
                _put(confined(self.root, name), changes[name][0])
            return problems(self.root, self.names)
        except (CampusError, ValidationError, OSError, ValueError):
            return None
        finally:
            for name in touched:
                _put(confined(self.root, name), changes[name][1])

    def new_problems(self, changes: dict[str, tuple[bytes | None, bytes | None]]) -> str | None:
        """The problems an edit of the anchored item introduced, as text the agent can act on.

        None when there are none, when the edit left that item alone, or when the item cannot
        be checked; the build gate still covers every edit.
        """
        self.thread.join()
        touched = set(changes) & set(self.names)
        if not touched:
            return None
        before = self.before
        if before is None or any(self.seen.get(name) != changes[name][0] for name in touched):
            before = self._restored(changes, touched)
        if before is None:
            return None
        try:
            after = problems(self.root, self.names)
        except (CampusError, ValidationError, OSError, ValueError):
            return None
        lines = [
            f"{key}: {detail}"
            for key, current in after.items()
            for signature, detail in current.items()
            if signature not in before.get(key, {})
        ]
        return "\n".join(lines)[:2000] or None


def _put(path: Path, body: bytes | None) -> None:
    if body is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(body)


def rebuild(root: Path) -> str | None:
    """Builds the local app; returns the build error a student or agent can act on."""
    from tum_mcp.course.app.build import build

    try:
        build(root, publish=False)
    except CampusError as error:
        return error.message
    except ValidationError as error:
        return str(error)[:2000]
    return None


def _titles(body: bytes | None) -> dict[str, str]:
    try:
        value = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {}
    blocks = value.get("blocks") if isinstance(value, dict) else None
    if isinstance(blocks, list):
        return {
            json.dumps(block, sort_keys=True): block.get("title") or value.get("title", "")
            for block in blocks
            if isinstance(block, dict)
        }
    return {"": value.get("title", "")} if isinstance(value, dict) else {}


def sections(changes: dict[str, tuple[bytes | None, bytes | None]]) -> list[str]:
    names: list[str] = []
    for before, after in changes.values():
        old, new = _titles(before), _titles(after)
        for title in [title for key, title in new.items() if key not in old] or list(new.values()):
            if title and title not in names:
                names.append(title)
    return names[:6]


def _folder(root: Path) -> Path:
    return private_path(root, "agent/snapshots")


def record(root: Path, changes: dict[str, tuple[bytes | None, bytes | None]]) -> str:
    edit = uuid4().hex
    folder = _folder(root) / edit
    folder.mkdir(mode=0o700, parents=True)
    manifest = {}
    for index, (name, (before, after)) in enumerate(changes.items()):
        if before is not None:
            private_write(folder / f"{index}.bin", before)
        manifest[name] = {
            "file": f"{index}.bin" if before is not None else None,
            "after": digest(after) if after is not None else None,
        }
    private_write(folder / "manifest.json", json.dumps(manifest).encode())
    edits = sorted(_folder(root).iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in edits[KEEP:]:
        shutil.rmtree(old, ignore_errors=True)
    return edit


def _manifest(root: Path, edit: str) -> dict | None:
    if not edit.isalnum():
        return None
    try:
        return json.loads((_folder(root) / edit / "manifest.json").read_bytes())
    except (OSError, json.JSONDecodeError):
        return None


def _matches(root: Path, manifest: dict, key: str) -> bool:
    """Whether every file still has the content the edit record expects under `key`."""
    for name, entry in manifest.items():
        current = read_bytes(confined(root, name))
        if (digest(current) if current is not None else None) != entry.get(key):
            return False
    return True


def _undone(root: Path, edit: str) -> bool:
    return (_folder(root) / edit / "undone").exists()


def undoable(root: Path, edit: str) -> bool:
    manifest = _manifest(root, edit)
    return manifest is not None and not _undone(root, edit) and _matches(root, manifest, "after")


def redoable(root: Path, edit: str) -> bool:
    manifest = _manifest(root, edit)
    return manifest is not None and _undone(root, edit) and _matches(root, manifest, "before")


def undo(root: Path, edit: str) -> None:
    """Puts the files back as they were before the edit, keeping the edited files for Redo."""
    if not undoable(root, edit):
        raise CampusError(Code.STALE_RESULT, "The page changed since this edit; undo is closed.")
    folder = _folder(root) / edit
    manifest = json.loads((folder / "manifest.json").read_bytes())
    writes = []
    for index, (name, entry) in enumerate(manifest.items()):
        current = read_bytes(confined(root, name))
        before = (folder / entry["file"]).read_bytes() if entry["file"] else None
        entry["redo"] = f"{index}.after" if current is not None else None
        if current is not None:
            private_write(folder / entry["redo"], current)
        entry["before"] = digest(before) if before is not None else None
        writes.append(Write(name, current, before))
    apply(root, tuple(writes))
    if error := rebuild(root):
        raise CampusError(Code.WORKSPACE_CONFLICT, f"Undo restored the files but: {error}")
    private_write(folder / "manifest.json", json.dumps(manifest).encode())
    private_write(folder / "undone", b"")


def redo(root: Path, edit: str) -> None:
    """Puts the agent's edit back after an Undo, while the files are as the Undo left them."""
    if not redoable(root, edit):
        raise CampusError(Code.STALE_RESULT, "The page changed since the undo; redo is closed.")
    folder = _folder(root) / edit
    manifest = json.loads((folder / "manifest.json").read_bytes())
    writes = tuple(
        Write(
            name,
            read_bytes(confined(root, name)),
            (folder / entry["redo"]).read_bytes() if entry.get("redo") else None,
        )
        for name, entry in manifest.items()
    )
    apply(root, writes)
    if error := rebuild(root):
        raise CampusError(Code.WORKSPACE_CONFLICT, f"Redo restored the edit but: {error}")
    (folder / "undone").unlink(missing_ok=True)
