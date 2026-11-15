"""An exercise's project: packed from real files on disk and checked against its snapshot."""

from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from tum_mcp.course.content.exercises import Exercise, ExerciseContent
from tum_mcp.course.content.store import read_document, write_document
from tum_mcp.course.project.store import confined
from tum_mcp.course.sources.repository import KEY, project_snapshot
from tum_mcp.errors import CampusError, Code

Origin = Literal["repository", "rebuilt", "authored"]


def _folder_files(folder: Path) -> dict[str, str]:
    if not folder.is_dir():
        raise CampusError(Code.INVALID_RESPONSE, f"{folder} is not a folder of files.")
    files: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        if (
            path.is_symlink()
            or not path.is_file()
            or any(part.startswith(".") for part in path.relative_to(folder).parts)
        ):
            continue
        try:
            files[path.relative_to(folder).as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise CampusError(Code.INVALID_RESPONSE, f"{path} is not UTF-8 text.") from None
    if not files:
        raise CampusError(Code.INVALID_RESPONSE, f"{folder} holds no files.")
    return files


def pack(
    root: Path,
    exercise_key: str,
    source: str,
    *,
    origin: Origin,
    editable: tuple[str, ...],
    solutions: Path | None = None,
    open_path: str | None = None,
    description: str | None = None,
    rebuilt_because: str | None = None,
) -> dict[str, JsonValue]:
    """Write the exercise's one files block from a snapshot or a starter folder.

    A snapshot source packs the template byte for byte; a folder packs authored starters.
    Each editable file takes its solved version from `solutions` at the same path; a solved
    file with no starter is a file the student creates, starting empty. Steps are kept, and
    the whole workspace is validated before anything is written."""
    if KEY.fullmatch(source):
        found = project_snapshot(root, source)
        if found is None:
            raise CampusError(
                Code.ACTION_REQUIRED, f"No snapshot {source}; run tum-mcp study repository first."
            )
        if origin != "repository":
            raise CampusError(Code.INVALID_RESPONSE, "A snapshot packs a repository project.")
        starters = found[1]
    else:
        if origin == "repository":
            raise CampusError(
                Code.INVALID_RESPONSE,
                "A repository project comes from its snapshot: pass --from artemis-ID.",
            )
        starters = _folder_files(
            confined(root, source) if not Path(source).is_absolute() else Path(source)
        )
    solved = _folder_files(solutions) if solutions else {}
    unknown = sorted(set(solved) - set(editable))
    if unknown:
        raise CampusError(Code.INVALID_RESPONSE, f"Solved files that are not editable: {unknown}.")
    missing = sorted(path for path in editable if path not in starters and path not in solved)
    if missing:
        raise CampusError(
            Code.INVALID_RESPONSE, f"Editable files with no starter or solution: {missing}."
        )
    files: list[dict[str, JsonValue]] = []
    for path in sorted(set(starters) | set(editable)):
        entry: dict[str, JsonValue] = {"path": path, "code": starters.get(path, "")}
        if path in editable:
            entry["editable"] = True
            if path in solved:
                entry["solution"] = solved[path]
        files.append(entry)

    document = read_document(root, "exercises")
    if document is None:
        raise CampusError(Code.ACTION_REQUIRED, "Write the exercise before packing its project.")
    exercise = next(
        (
            item
            for group in document["sets"]
            for item in group["exercises"]
            if item["key"] == exercise_key
        ),
        None,
    )
    if exercise is None:
        raise CampusError(Code.INVALID_RESPONSE, f"No exercise {exercise_key} in Exercises.")
    statement = exercise["statement"]
    index = next((i for i, block in enumerate(statement) if block["kind"] == "files"), None)
    current = statement[index] if index is not None else {}
    declared = [item["key"] for item in exercise["sources"]]
    block: dict[str, JsonValue] = {
        "kind": "files",
        "key": current.get("key", "project"),
        "sources": [source] if source in declared else current.get("sources", declared[:1]),
        "description": description or current.get("description"),
        "files": files,
    }
    if not block["description"]:
        raise CampusError(Code.INVALID_RESPONSE, "Describe the project with --description.")
    if open_path or current.get("open"):
        block["open"] = open_path or current["open"]
    if origin != "repository":
        block["origin"] = origin
    if rebuilt_because:
        block["rebuilt_because"] = rebuilt_because
    if index is None:
        statement.append(block)
    else:
        statement[index] = block
    content = ExerciseContent.model_validate(document)
    write_document(root, "exercises", document)
    packed = next(
        item for group in content.sets for item in group.exercises if item.key == exercise_key
    )
    return {
        "exercise": exercise_key,
        "origin": origin,
        "files": len(files),
        "editable": sorted(editable),
        "unsolved": sorted(path for path in editable if path not in solved),
        "problems": drift(root, packed),
    }


def drift(root: Path, exercise: Exercise) -> list[str]:
    """How a repository project differs from its snapshot; empty when it is faithful."""
    block = next((item for item in exercise.statement if item.kind == "files"), None)
    if block is None or block.origin != "repository":
        return []
    keys = [key for key in block.sources if KEY.fullmatch(key)]
    found = project_snapshot(root, keys[0]) if keys else None
    if found is None:
        return [
            "No repository snapshot backs this project. Read it with artemis_get_repository and "
            "tum-mcp study repository, then pack it with tum-mcp study files."
        ]
    snapshot = found[1]
    files = {item.path: item for item in block.files}
    problems = [f"{path} is missing." for path in sorted(set(snapshot) - set(files))]
    problems += [
        f"{path} differs from the template."
        for path in sorted(set(snapshot) & set(files))
        if files[path].code != snapshot[path]
    ]
    problems += [
        f"{path} is not in the template; only a new editable file that starts empty may be added."
        for path in sorted(set(files) - set(snapshot))
        if not files[path].editable or files[path].code
    ]
    return problems
