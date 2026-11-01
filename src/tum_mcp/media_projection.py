"""Exact file and source identities for private, read-only media review."""

from pathlib import Path
from typing import Literal

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_content import SourceVersion
from tum_mcp.study_models import StudyState
from tum_mcp.study_store import confined
from tum_mcp.video_content import canonical, sha256
from tum_mcp.video_project import _hash_file

MEDIA_RUBRIC_VERSION = 1


def file_hash(
    root: Path,
    relative: str,
    expected: str,
    size: int | None = None,
) -> str:
    path = confined(root, relative)
    if not path.is_file():
        raise CampusError(Code.INVALID_RESPONSE, f"Missing media file: {relative}.")
    if size is not None and path.stat().st_size != size:
        raise CampusError(Code.INVALID_RESPONSE, f"Media file size changed: {relative}.")
    actual = _hash_file(path)
    if actual != expected:
        raise CampusError(Code.INVALID_RESPONSE, f"Media file bytes changed: {relative}.")
    return actual


def guidance_hash(modality: Literal["audio", "video"]) -> str:
    folder = Path(__file__).parent / "bundled/skills" / f"{modality}-notes"
    files = [
        (p.relative_to(folder).as_posix(), _hash_file(p)) for p in sorted(folder.rglob("*.md"))
    ]
    return sha256(canonical([list(item) for item in files]))


def source_problems(
    root: Path,
    state: StudyState,
    references: tuple[SourceVersion, ...],
) -> tuple[str, ...]:
    resources = {item.resource.key: item for item in state.resources}
    problems = []
    for source in references:
        resource = resources.get(source.key)
        if (
            resource is None
            or resource.status != "current"
            or resource.sha256 != source.sha256
            or resource.path is None
        ):
            problems.append(f"source_changed:{source.key}")
            continue
        try:
            file_hash(root, resource.path, source.sha256)
        except (CampusError, OSError):
            problems.append(f"source_changed:{source.key}")
    return tuple(problems)
