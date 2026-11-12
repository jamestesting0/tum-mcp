"""Lecture figures cropped from source pages into the app, with where each came from."""

import io
import json
from pathlib import Path

from tum_mcp.course.content.figures import FIGURE_IMAGE, IMAGE_BYTES
from tum_mcp.course.project.models import StudyState
from tum_mcp.course.project.paths import app_path
from tum_mcp.course.project.store import confined, digest, load_state, private_name
from tum_mcp.course.sources.text import material_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.errors import MoodleError

PROVENANCE = ".tum-mcp/figures.json"


def _pdf(root: Path, key: str, state: StudyState | None) -> tuple[bytes, str]:
    _, body, sha256 = material_bytes(root, state or load_state(root), key)
    if not body.startswith(b"%PDF-"):
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Figures are cropped from PDF pages.")
    return body, sha256


def page_regions(root: Path, key: str, page: int, state: StudyState | None = None) -> dict:
    """List a page's figure regions and write a preview with each region numbered."""
    from tum_mcp.moodle.extract_worker import pdf_figure_regions

    root = root.expanduser().resolve()
    body, _ = _pdf(root, key, state)
    try:
        found = pdf_figure_regions(body, page)
    except MoodleError as error:
        raise CampusError(Code.INVALID_RESPONSE, error.message) from None
    preview = private_name(root, "out/figure-page.png")
    target = confined(root, preview)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_write(target, found["preview"])
    return {
        "source": key,
        "page": page,
        "preview": preview,
        "regions": [{"region": n, "box": box} for n, box in enumerate(found["regions"], 1)],
    }


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def crop_figure(
    root: Path,
    key: str,
    page: int,
    name: str,
    *,
    regions: list[int] | None = None,
    box: list[float] | None = None,
    state: StudyState | None = None,
) -> dict:
    """Crop numbered regions (merged) or a box of a page into `figures/<name>.png`."""
    from tum_mcp.moodle.extract_worker import crop_pdf_page, pdf_figure_regions

    image = f"figures/{name}.png"
    if not FIGURE_IMAGE.fullmatch(image):
        raise CampusError(
            Code.INVALID_RESPONSE, "Name a figure with lowercase letters, digits and -."
        )
    if (regions is None) == (box is None):
        raise CampusError(Code.INVALID_RESPONSE, "Give --region or --box.")
    root = root.expanduser().resolve()
    body, sha256 = _pdf(root, key, state)
    try:
        if regions is not None:
            found = pdf_figure_regions(body, page)["regions"]
            if not regions or any(not 1 <= n <= len(found) for n in regions):
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Page {page} has regions 1-{len(found)}; list them first.",
                )
        chosen = _union([found[n - 1] for n in regions]) if regions is not None else box or []
        png = crop_pdf_page(body, page, chosen)
    except MoodleError as error:
        raise CampusError(Code.INVALID_RESPONSE, error.message) from None
    if len(png) > IMAGE_BYTES:
        raise CampusError(Code.INVALID_RESPONSE, "The crop exceeds 2 MB; choose a smaller box.")
    target = app_path(root, image)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    provenance = confined(root, PROVENANCE)
    records = json.loads(provenance.read_text(encoding="utf-8")) if provenance.is_file() else {}
    records[image] = {
        "source": key,
        "page": page,
        "box": [round(value, 4) for value in chosen],
        "source_sha256": sha256,
        "sha256": digest(png),
    }
    provenance.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    grid = private_name(root, "out/figure-grid.png")
    confined(root, grid).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_write(confined(root, grid), _grid(png))
    return {
        "image": image,
        "sources": [key],
        "pages": str(page),
        "box": records[image]["box"],
        "grid": grid,
    }


def _grid(png: bytes) -> bytes:
    """The crop under a labelled tenths grid, to read off walkthrough region coordinates."""
    from PIL import Image, ImageDraw

    image = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for tenth in range(1, 10):
        x, y = width * tenth / 10, height * tenth / 10
        draw.line([(x, 0), (x, height)], fill=(214, 40, 40), width=1)
        draw.line([(0, y), (width, y)], fill=(214, 40, 40), width=1)
        draw.text((x + 3, 3), f".{tenth}", fill=(214, 40, 40), font_size=16)
        draw.text((3, y + 3), f".{tenth}", fill=(214, 40, 40), font_size=16)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def figure_provenance(root: Path) -> dict[str, dict]:
    path = confined(root, PROVENANCE)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
