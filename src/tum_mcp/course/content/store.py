"""Workspace content stored one item per file and read back as one validated document.

Agents edit a unit, problem, entry or lecture in its own small file; every reader assembles
the same document the models validate, so nothing else needs to know the layout.
"""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tum_mcp.course.project.paths import APP, app_path
from tum_mcp.course.project.store import Write, apply, confined, digest, read_bytes
from tum_mcp.errors import CampusError, Code

LIMIT = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Layout:
    folder: str
    index: str
    # Fields whose items live in their own files, each under its subfolder, by item key.
    collections: tuple[str, ...] = ()


LAYOUTS = {
    "study": Layout("study", "course.json", ("units",)),
    "exercises": Layout("exercises", "sets.json"),
    "exam": Layout("exam", "exam.json", ("concepts", "patterns", "mocks")),
    "lectures": Layout("lectures", "lectures.json", ("lectures",)),
}

Read = Callable[[Path], bytes | None]


def index_name(workspace: str) -> str:
    layout = LAYOUTS[workspace]
    return f"{APP}/{layout.folder}/{layout.index}"


def present(root: Path, workspace: str) -> bool:
    return app_path(root, f"{LAYOUTS[workspace].folder}/{LAYOUTS[workspace].index}").exists()


def _item_names(workspace: str, index: dict) -> list[tuple[str, str]]:
    folder = LAYOUTS[workspace].folder
    if workspace == "exercises":
        return [
            (f"{APP}/{folder}/{group['key']}/{key}.json", key)
            for group in index.get("sets", [])
            for key in group.get("exercises", [])
        ]
    return [
        (f"{APP}/{folder}/{field}/{key}.json", key)
        for field in LAYOUTS[workspace].collections
        for key in index.get(field, [])
    ]


def locate(workspace: str, document: dict, loc: tuple) -> str:
    """Where a validation error sits: the item's own file and the path inside it."""
    parts = list(loc)
    name = index_name(workspace)
    try:
        if workspace == "exercises" and parts[:1] == ["sets"] and parts[2:3] == ["exercises"]:
            group = document["sets"][parts[1]]
            key = group["exercises"][parts[3]]["key"]
            name, parts = f"{APP}/exercises/{group['key']}/{key}.json", parts[4:]
        elif parts and parts[0] in LAYOUTS[workspace].collections and len(parts) > 1:
            key = document[parts[0]][parts[1]]["key"]
            name, parts = f"{APP}/{LAYOUTS[workspace].folder}/{parts[0]}/{key}.json", parts[2:]
    except (IndexError, KeyError, TypeError):
        pass
    return f"{name} at {'.'.join(map(str, parts)) or 'top level'}"


def _load(name: str, body: bytes) -> dict:
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise CampusError(Code.INVALID_RESPONSE, f"{name} is not valid JSON.") from None
    if not isinstance(value, dict):
        raise CampusError(Code.INVALID_RESPONSE, f"{name} must hold one JSON object.")
    return value


def read_document(root: Path, workspace: str, read: Read | None = None) -> dict | None:
    """The whole workspace document, or None when the workspace is not prepared."""
    read = read or read_bytes
    layout = LAYOUTS[workspace]
    index_body = read(confined(root, index_name(workspace)))
    if index_body is None:
        return None
    total = len(index_body)
    index = _load(index_name(workspace), index_body)
    items: dict[str, dict] = {}
    for name, key in _item_names(workspace, index):
        body = read(confined(root, name))
        if body is None:
            raise CampusError(
                Code.INVALID_RESPONSE,
                f"{index_name(workspace)} lists {key}, but {name} is missing.",
            )
        total += len(body)
        if total > LIMIT:
            raise CampusError(Code.INVALID_RESPONSE, f"{layout.folder} content exceeds 8 MiB.")
        item = _load(name, body)
        if item.get("key") != key:
            raise CampusError(
                Code.INVALID_RESPONSE, f"{name} must hold the item keyed {key}, not its own key."
            )
        items[name] = item
    listed = set(items)
    folder = confined(root, f"{APP}/{layout.folder}")
    for path in folder.rglob("*.json"):
        name = path.relative_to(root).as_posix()
        if name != index_name(workspace) and name not in listed:
            raise CampusError(
                Code.INVALID_RESPONSE,
                f"{name} is not listed in {index_name(workspace)}; list its key or delete it.",
            )
    document = dict(index)
    if workspace == "exercises":
        document["sets"] = [
            {
                **group,
                "exercises": [
                    items[f"{APP}/{layout.folder}/{group['key']}/{key}.json"]
                    for key in group.get("exercises", [])
                ],
            }
            for group in index.get("sets", [])
        ]
    else:
        for field in layout.collections:
            if field in index:
                document[field] = [
                    items[f"{APP}/{layout.folder}/{field}/{key}.json"] for key in index[field]
                ]
    return document


def read_json(root: Path, workspace: str, read: Read | None = None) -> bytes | None:
    """The assembled document as JSON, so models validate it exactly as authored."""
    document = read_document(root, workspace, read)
    return None if document is None else json.dumps(document, ensure_ascii=False).encode()


def document_digest(root: Path, workspace: str) -> str | None:
    body = read_json(root, workspace)
    return None if body is None else digest(body)


def _encode(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def split(workspace: str, document: dict) -> dict[str, bytes]:
    layout = LAYOUTS[workspace]
    index = dict(document)
    files: dict[str, bytes] = {}
    if workspace == "exercises":
        index["sets"] = []
        for group in document.get("sets", []):
            exercises = group.get("exercises", [])
            index["sets"].append({**group, "exercises": [item["key"] for item in exercises]})
            for item in exercises:
                files[f"{APP}/{layout.folder}/{group['key']}/{item['key']}.json"] = _encode(item)
    else:
        for field in layout.collections:
            if field in document:
                index[field] = [item["key"] for item in document[field]]
                for item in document[field]:
                    files[f"{APP}/{layout.folder}/{field}/{item['key']}.json"] = _encode(item)
    files[index_name(workspace)] = _encode(index)
    return files


def document_writes(root: Path, workspace: str, document: dict) -> tuple[Write, ...]:
    """Writes that store the document and remove item files it no longer lists."""
    desired = split(workspace, document)
    folder = confined(root, f"{APP}/{LAYOUTS[workspace].folder}")
    existing = (
        {path.relative_to(root).as_posix() for path in folder.rglob("*.json")}
        if folder.exists()
        else set()
    )
    writes = [Write(name, read_bytes(confined(root, name)), body) for name, body in desired.items()]
    writes += [
        Write(name, read_bytes(confined(root, name)), None)
        for name in sorted(existing - set(desired))
    ]
    return tuple(writes)


def write_document(root: Path, workspace: str, document: dict) -> None:
    apply(root, document_writes(root, workspace, document))


def remove_document(root: Path, workspace: str) -> None:
    folder = confined(root, f"{APP}/{LAYOUTS[workspace].folder}")
    if folder.exists():
        shutil.rmtree(folder)
