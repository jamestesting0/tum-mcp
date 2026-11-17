"""Import a file the user already holds as a private, never-published local source."""

import json
import re
import tempfile
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from tum_mcp.course.project.models import Binding, Coverage, Kind, Resource, Snapshot
from tum_mcp.course.project.store import digest, load_state
from tum_mcp.course.project.sync import sync
from tum_mcp.errors import CampusError, Code

MAX_FILE = 50 * 1024 * 1024
SUFFIXES = {
    ".pdf": ".pdf",
    ".md": ".md",
    ".txt": ".txt",
    ".png": ".png",
    ".jpg": ".jpg",
    ".jpeg": ".jpg",
}
# Code and notebooks become Markdown text with line and cell locators; nothing is run.
CODE = {
    ".py": "python",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".js": "javascript",
    ".ts": "typescript",
    ".r": "r",
    ".m": "matlab",
    ".jl": "julia",
    ".hs": "haskell",
    ".sql": "sql",
}


def _numbered(code: str) -> str:
    lines = code.splitlines() or [""]
    width = len(str(len(lines)))
    return "\n".join(f"{number:>{width}} | {line}" for number, line in enumerate(lines, 1))


def code_text(name: str, code: str, language: str) -> str:
    """A code file as text: each line keeps its number, so a citation can name it."""
    body = _numbered(code)
    return f"# {name}\n\nNever executed. Lines are numbered.\n\n```{language}\n{body}\n```\n"


def notebook_text(name: str, data: bytes) -> str:
    """A notebook as text: one section per cell; saved outputs are marked as not re-run."""
    try:
        notebook = json.loads(data)
        cells = notebook["cells"]
        language = notebook.get("metadata", {}).get("kernelspec", {}).get("language", "python")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CampusError(Code.INVALID_RESPONSE, "The notebook is not valid JSON.") from None
    parts = [f"# {name}\n\nNever executed. Saved outputs were not re-run and are unverified."]
    for number, cell in enumerate(cells, 1):
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else str(source)
        kind = cell.get("cell_type", "code")
        if kind == "markdown":
            parts.append(f"## Cell {number} (text)\n\n{source}")
            continue
        parts.append(f"## Cell {number} ({kind})\n\n```{language}\n{_numbered(source)}\n```")
        shown = []
        for output in cell.get("outputs", []):
            text = output.get("text") or output.get("data", {}).get("text/plain") or ""
            shown.append("".join(text) if isinstance(text, list) else str(text))
        if any(item.strip() for item in shown):
            parts.append(
                "Saved output (unverified):\n\n```text\n" + "".join(shown).rstrip() + "\n```"
            )
    return "\n\n".join(parts) + "\n"


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
    original = file.suffix.lower()
    suffix = ".md" if original == ".ipynb" or original in CODE else SUFFIXES.get(original)
    if suffix is None:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Import a PDF, text, Markdown, image, notebook or code file.",
        )
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_FILE:
        raise CampusError(Code.INVALID_RESPONSE, "Choose a regular file of at most 50 MiB.")
    data = file.read_bytes()
    if original == ".ipynb":
        data = notebook_text(file.name, data).encode()
    elif original in CODE:
        data = code_text(file.name, data.decode("utf-8", "replace"), CODE[original]).encode()
    if suffix == ".pdf":
        from tum_mcp.moodle.errors import MoodleError
        from tum_mcp.moodle.extract_worker import validate_pdf

        try:
            validate_pdf(data)
        except MoodleError as error:
            raise CampusError(Code.INVALID_RESPONSE, error.message) from None
    sha256 = digest(data)
    local = next((item for item in state.course.bindings if item.provider == "local"), None)
    # A file the course already holds is that resource, whichever binding fetched it.
    for item in state.resources:
        if item.sha256 == sha256 and item.path:
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
        (staging / f"upload{suffix}").write_bytes(data)
        path = staging / "snapshot.json"
        path.write_text(snapshot.model_dump_json(exclude_none=True), encoding="utf-8")
        sync(root, path)
    item = next(entry for entry in load_state(root).resources if entry.resource.key == key)
    if item.path is None or item.sha256 != sha256:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The import destination needs local review.")
    return ImportReport(key=key, sha256=sha256, imported=True, path=item.path)
