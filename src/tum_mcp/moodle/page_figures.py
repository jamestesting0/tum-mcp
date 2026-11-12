"""Figure regions of a PDF page and their crops; runs only inside the bounded extract worker.

Boxes are page fractions `[x0, y0, x1, y1]` with the origin at the top left.
"""

import io
from typing import Final

import pypdfium2
import pypdfium2.raw as pdfium
from PIL import Image, ImageChops, ImageDraw

GRAPHICS: Final = {pdfium.FPDF_PAGEOBJ_PATH, pdfium.FPDF_PAGEOBJ_IMAGE, pdfium.FPDF_PAGEOBJ_SHADING}
CROP_EDGE: Final = 1400
PREVIEW_EDGE: Final = 1200
MAX_SCALE: Final = 8.0
MAX_REGIONS: Final = 8

Box = list[float]


def _fractions(bounds: tuple[float, float, float, float], width: float, height: float) -> Box:
    left, bottom, right, top = bounds
    return [
        min(max(left / width, 0.0), 1.0),
        min(max(1 - top / height, 0.0), 1.0),
        min(max(right / width, 0.0), 1.0),
        min(max(1 - bottom / height, 0.0), 1.0),
    ]


def _area(box: Box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _near(first: Box, second: Box, gap: float) -> bool:
    return (
        first[0] <= second[2] + gap
        and second[0] <= first[2] + gap
        and first[1] <= second[3] + gap
        and second[1] <= first[3] + gap
    )


def _merge(boxes: list[Box], gap: float) -> list[Box]:
    merged: list[Box] = []
    for box in boxes:
        box = list(box)
        joined = True
        while joined:
            joined = False
            for other in merged:
                if _near(box, other, gap):
                    merged.remove(other)
                    box = [
                        min(box[0], other[0]),
                        min(box[1], other[1]),
                        max(box[2], other[2]),
                        max(box[3], other[3]),
                    ]
                    joined = True
                    break
        merged.append(box)
    return merged


def _band(box: Box) -> bool:
    """A slide's title bar or footer: a full-width strip at the top or bottom."""
    return box[2] - box[0] > 0.9 and (box[3] < 0.2 or box[1] > 0.9)


def regions(body: bytes, number: int) -> tuple[list[Box], bytes]:
    """Graphic clusters on the page, with the text labels touching them, largest first."""
    document = pypdfium2.PdfDocument(body)
    try:
        if not 1 <= number <= len(document):
            raise ValueError("Page out of range")
        page = document[number - 1]
        width, height = page.get_size()
        graphics: list[Box] = []
        labels: list[Box] = []
        for item in page.get_objects(max_depth=4):
            box = _fractions(item.get_bounds(), width, height)
            if _area(box) <= 0 or _area(box) > 0.85:
                continue
            if item.type in GRAPHICS:
                graphics.append(box)
            elif item.type == pdfium.FPDF_PAGEOBJ_TEXT:
                labels.append(box)
        clusters = [box for box in _merge(graphics, 0.015) if not _band(box)]
        found: list[Box] = []
        for box in clusters:
            # City names, axis labels and tile numbers belong to the figure they touch.
            for label in labels:
                if _near(box, label, 0.02) and not _band(label) and label[2] - label[0] < 0.5:
                    box = [
                        min(box[0], label[0]),
                        min(box[1], label[1]),
                        max(box[2], label[2]),
                        max(box[3], label[3]),
                    ]
            found.append(box)
        found = [box for box in _merge(found, 0.0) if _area(box) >= 0.02]
        found.sort(key=_area, reverse=True)
        found = [[round(value, 4) for value in box] for box in found[:MAX_REGIONS]]
        preview = _preview(page, found)
        page.close()
        return found, preview
    finally:
        document.close()


def _preview(page: pypdfium2.PdfPage, found: list[Box]) -> bytes:
    bitmap = page.render(scale=PREVIEW_EDGE / max(page.get_size()))
    try:
        image = bitmap.to_pil().convert("RGB")
    finally:
        bitmap.close()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for index, box in enumerate(found, start=1):
        corners = (box[0] * width, box[1] * height, box[2] * width, box[3] * height)
        draw.rectangle(corners, outline=(214, 40, 40), width=4)
        tag = (corners[0], max(corners[1] - 30, 0), corners[0] + 34, max(corners[1] - 30, 0) + 30)
        draw.rectangle(tag, fill=(214, 40, 40))
        draw.text((tag[0] + 10, tag[1] + 6), str(index), fill=(255, 255, 255), font_size=20)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def crop(body: bytes, number: int, box: Box) -> bytes:
    """Render one region sharply, then trim the empty margin around the drawing."""
    if len(box) != 4 or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError("A box is x0,y0,x1,y1 within 0..1 with x0 < x1 and y0 < y1")
    document = pypdfium2.PdfDocument(body)
    try:
        if not 1 <= number <= len(document):
            raise ValueError("Page out of range")
        page = document[number - 1]
        width, height = page.get_size()
        long_edge = max((box[2] - box[0]) * width, (box[3] - box[1]) * height)
        scale = min(CROP_EDGE / long_edge, MAX_SCALE)
        margins = (box[0] * width, (1 - box[3]) * height, (1 - box[2]) * width, box[1] * height)
        bitmap = page.render(scale=scale, crop=margins)
        try:
            image = bitmap.to_pil().convert("RGB")
        finally:
            bitmap.close()
            page.close()
    finally:
        document.close()
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    content = (
        ImageChops.difference(image, background).convert("L").point(lambda v: 255 if v > 24 else 0)
    )
    if bounds := content.getbbox():
        pad = 16
        image = image.crop(
            (
                max(bounds[0] - pad, 0),
                max(bounds[1] - pad, 0),
                min(bounds[2] + pad, image.width),
                min(bounds[3] + pad, image.height),
            )
        )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
