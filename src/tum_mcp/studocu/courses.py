"""Locally cached evidence of Studocu courses returned for TUM."""

import unicodedata
from typing import Annotated, Literal

from filelock import FileLock
from pydantic import Field, ValidationError

from tum_mcp.client_installs import Write, commit_writes, read_owned_file
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen, config_dir, config_path


class Courses(Frozen):
    schema_version: Literal[1] = 1
    institution_id: Literal[92] = 92
    course_ids: tuple[Annotated[int, Field(strict=True, gt=0, le=2147483647)], ...] = Field(
        default=(), max_length=10000
    )
    names: dict[str, str] = Field(default_factory=dict, max_length=10000)


def _load() -> Courses:
    path = config_path() / "studocu-courses.json"
    if not path.exists():
        return Courses()
    try:
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise ValueError
        return Courses.model_validate_json(path.read_bytes())
    except (OSError, ValueError, ValidationError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Studocu course evidence needs review."
        ) from None


def known_course(course_id: str) -> bool:
    return int(course_id) in _load().course_ids


def matches_course(course_id: str, title: str) -> bool:
    """Only an exact normalized provider title establishes an automatic match."""
    name = _load().names.get(course_id)
    if not name:
        return False

    def normalize(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    return normalize(name) == normalize(title)


def record_courses(items: list[dict]) -> None:
    ids = {
        item["course_id"]
        for item in items
        if isinstance(item, dict)
        and type(item.get("course_id")) is int
        and 0 < item["course_id"] <= 2147483647
        and item.get("institution_id") == 92
    }
    if not ids:
        return
    with FileLock(str(config_dir() / "studocu-courses.lock")):
        current = _load()
        path = config_path() / "studocu-courses.json"
        before = read_owned_file(path, config_dir().resolve())
        names = dict(current.names)
        for item in items:
            if (
                isinstance(item, dict)
                and item.get("course_id") in ids
                and isinstance(item.get("name"), str)
            ):
                title = item["name"].strip()
                if title and len(title) <= 200:
                    names[str(item["course_id"])] = title
        after = Courses(course_ids=tuple(sorted(set(current.course_ids) | ids)), names=names)
        commit_writes((Write(path, before, after.model_dump_json(indent=2).encode()),))
