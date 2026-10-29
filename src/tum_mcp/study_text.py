"""Page text for stored course materials, extracted once per content hash."""

from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.errors import MoodleError
from tum_mcp.settings import Frozen
from tum_mcp.study_models import Digest, StudyState
from tum_mcp.study_store import confined, digest, load_state, private_path

# Bump when extraction output changes so older cache records are recomputed.
EXTRACTOR = 1
MAX_FILE = 50 * 1024 * 1024


class TextPage(Frozen):
    number: int = Field(ge=1)
    text: str
    available: bool


class TextRecord(Frozen):
    extractor: int
    sha256: Digest
    kind: Literal["pdf", "text", "office", "image"]
    pages: tuple[TextPage, ...]
    truncated: bool = False

    @property
    def needs_visual(self) -> tuple[int, ...]:
        """Pages without a text layer: scans, figures or slides that must be viewed."""
        return tuple(page.number for page in self.pages if not page.available)


def _kind(path: Path, body: bytes) -> Literal["pdf", "text", "office", "image"]:
    if body.startswith(b"%PDF-"):
        return "pdf"
    if body.startswith(b"PK\x03\x04"):
        return "office"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return "image"
    return "text"


def _extract(path: Path, body: bytes, sha256: str) -> TextRecord:
    from tum_mcp.moodle.extract_worker import read_pdf_text, run_extraction

    kind = _kind(path, body)
    try:
        match kind:
            case "pdf":
                result = read_pdf_text(body)
                pages = tuple(
                    TextPage(
                        number=item["number"],
                        text=item["text"],
                        available=item["text_available"],
                    )
                    for item in result["pages"]
                )
                truncated = bool(result.get("truncated"))
            case "office":
                extracted = run_extraction(body, "application/octet-stream")
                pages = tuple(
                    TextPage(number=page.number, text=page.text, available=bool(page.text.strip()))
                    for page in extracted.pages
                )
                truncated = bool(extracted.warnings)
            case "image":
                pages, truncated = (TextPage(number=1, text="", available=False),), False
            case "text":
                text = body.decode("utf-8")
                pages = (TextPage(number=1, text=text, available=bool(text.strip())),)
                truncated = False
    except UnicodeDecodeError:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Text extraction reads PDF, Office, text and image files."
        ) from None
    except (MoodleError, KeyError, TypeError, ValidationError) as error:
        message = error.message if isinstance(error, MoodleError) else "unexpected output"
        raise CampusError(Code.INVALID_RESPONSE, f"Text extraction failed: {message}") from None
    return TextRecord(
        extractor=EXTRACTOR, sha256=sha256, kind=kind, pages=pages, truncated=truncated
    )


def material_bytes(root: Path, state: StudyState, key: str) -> tuple[Path, bytes, str]:
    """Read one current material and prove it still matches its inventory hash."""
    item = next((entry for entry in state.resources if entry.resource.key == key), None)
    if item is None:
        raise CampusError(Code.ACTION_REQUIRED, f"No inventory resource has key {key}.")
    relative = item.path
    if item.status != "current" or relative is None or item.sha256 is None:
        raise CampusError(Code.STALE_RESULT, f"Material {key} is not current; sync it first.")
    path = confined(root, relative)
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise CampusError(Code.INVALID_RESPONSE, f"Material {key} is missing or exceeds 50 MiB.")
    body = path.read_bytes()
    if digest(body) != item.sha256:
        raise CampusError(Code.STALE_RESULT, f"Material {key} changed locally; review and resync.")
    return path, body, item.sha256


def cached_record(root: Path, sha256: str) -> TextRecord | None:
    path = private_path(root, f"cache/text/{sha256}.json")
    if not path.is_file():
        return None
    try:
        record = TextRecord.model_validate_json(path.read_bytes())
    except ValidationError:
        return None
    return record if record.extractor == EXTRACTOR and record.sha256 == sha256 else None


def document_text(root: Path, key: str, state: StudyState | None = None) -> TextRecord:
    """Return a material's page text, extracting it at most once per content hash."""
    root = root.expanduser().resolve()
    state = state or load_state(root)
    path, body, sha256 = material_bytes(root, state, key)
    cached = cached_record(root, sha256)
    if cached is not None:
        return cached
    record = _extract(path, body, sha256)
    target = private_path(root, f"cache/text/{sha256}.json")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_write(target, record.model_dump_json().encode())
    return record


def parse_pages(value: str, total: int) -> range:
    """Parse "4" or "2-9" into a page range within a document."""
    try:
        first, _, last = value.partition("-")
        start, end = int(first), int(last or first)
    except ValueError:
        raise CampusError(Code.INVALID_RESPONSE, "Use --pages N or --pages FIRST-LAST.") from None
    if not 1 <= start <= end <= total:
        raise CampusError(Code.INVALID_RESPONSE, f"Pages must lie within 1-{total}.")
    return range(start, end + 1)


def text_view(record: TextRecord, key: str, pages: str | None) -> dict:
    chosen = parse_pages(pages, len(record.pages)) if pages else range(1, len(record.pages) + 1)
    return {
        "key": key,
        "sha256": record.sha256,
        "kind": record.kind,
        "total_pages": len(record.pages),
        "truncated": record.truncated,
        "needs_visual": list(record.needs_visual),
        "pages": [record.pages[number - 1].model_dump() for number in chosen],
    }
