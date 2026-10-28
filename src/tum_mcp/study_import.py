"""Import a file the user already holds as a private, never-published local source."""

import re
import shutil
import tempfile
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_models import Binding, Coverage, Kind, Resource, Snapshot
from tum_mcp.study_store import digest, load_state
from tum_mcp.study_sync import sync

MAX_FILE = 50 * 1024 * 1024
SUFFIXES = {
    ".pdf": ".pdf",
    ".md": ".md",
    ".txt": ".txt",
    ".png": ".png",
    ".jpg": ".jpg",
    ".jpeg": ".jpg",
}


class ImportReport(BaseModel):
    key: str
    sha256: str
    imported: bool
    path: str


def _slug(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", "-", ascii_title.casefold()).strip("-")
    return (value or "file")[:80]


def import_file(project: Path, file: Path, kind: Kind, title: str) -> ImportReport:
    root = project.expanduser().resolve()
    state = load_state(root)
    title = title.strip()
    if not title or len(title) > 300:
        raise CampusError(Code.INVALID_RESPONSE, "Give the file a title of at most 300 characters.")
    suffix = SUFFIXES.get(file.suffix.lower())
    if suffix is None:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Import a PDF, text, Markdown or image file."
        )
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_FILE:
        raise CampusError(Code.INVALID_RESPONSE, "Choose a regular file of at most 50 MiB.")
    data = file.read_bytes()
    if suffix == ".pdf":
        from tum_mcp.moodle.errors import MoodleError
        from tum_mcp.moodle.extract_worker import validate_pdf

        try:
            validate_pdf(data)
        except MoodleError as error:
            raise CampusError(Code.INVALID_RESPONSE, error.message) from None
    sha256 = digest(data)
    local = next((item for item in state.course.bindings if item.provider == "local"), None)
    if local is not None:
        for item in state.resources:
            if item.resource.binding == local.key and item.sha256 == sha256 and item.path:
                return ImportReport(
                    key=item.resource.key, sha256=sha256, imported=False, path=item.path
                )
    if local is None:
        used = {item.key for item in state.course.bindings}
        local = Binding(
            key=next(name for name in ("local", "local-files", "user-files") if name not in used),
            provider="local",
            course_id="local",
        )
        course = state.course.model_copy(update={"bindings": (*state.course.bindings, local)})
    else:
        course = state.course
    keys = {item.resource.key for item in state.resources}
    stem = f"local-{_slug(title)}"
    key = next(
        candidate
        for candidate in (stem, *(f"{stem}-{number}" for number in range(2, 1000)))
        if candidate not in keys
    )
    snapshot = Snapshot(
        schema_version=state.schema_version,
        course=course,
        coverage=(
            Coverage(
                binding=local.key,
                status="partial",
                checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
                note="Files the user imported with study import.",
            ),
        ),
        resources=(
            Resource(
                key=key,
                binding=local.key,
                kind=kind,
                title=title,
                revision=sha256,
                source_file=f"upload{suffix}",
            ),
        ),
        retained_bindings=tuple(
            item.key for item in state.course.bindings if item.key != local.key
        ),
    )
    with tempfile.TemporaryDirectory(prefix="tum-import-") as temporary:
        staging = Path(temporary)
        shutil.copyfile(file, staging / f"upload{suffix}")
        path = staging / "snapshot.json"
        path.write_text(snapshot.model_dump_json(exclude_none=True), encoding="utf-8")
        sync(root, path)
    item = next(entry for entry in load_state(root).resources if entry.resource.key == key)
    if item.path is None or item.sha256 != sha256:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The import destination needs local review.")
    return ImportReport(key=key, sha256=sha256, imported=True, path=item.path)
