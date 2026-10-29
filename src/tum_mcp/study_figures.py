"""Figures: SVG drawings checked against an allowlist, or images in the app's figures folder.

A figure shows what an idea looks like (an arm with its angles, a grid world, a circuit), so
authors may draw freely; the allowlist keeps scripts, links, external resources and fixed
colours out, and theme classes colour the drawing in light and dark mode.
"""

import math
import re
from collections.abc import Iterator
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from pydantic import JsonValue

from tum_mcp.errors import CampusError, Code

FIGURE_IMAGE = re.compile(r"figures/[a-z0-9][a-z0-9-]{0,80}\.(png|jpg|jpeg|webp)\Z")
IMAGE_BYTES = 2 * 1024**2
SIGNATURES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "webp": (b"RIFF",),
}
SVG_ELEMENTS = frozenset(
    {
        "svg",
        "g",
        "line",
        "polyline",
        "polygon",
        "path",
        "rect",
        "circle",
        "ellipse",
        "text",
        "tspan",
        "defs",
        "marker",
        "title",
    }
)
SVG_ATTRIBUTES = frozenset(
    {
        "viewBox",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "width",
        "height",
        "points",
        "d",
        "transform",
        "class",
        "fill",
        "stroke",
        "stroke-width",
        "stroke-dasharray",
        "stroke-linecap",
        "stroke-linejoin",
        "text-anchor",
        "dominant-baseline",
        "font-size",
        "font-weight",
        "font-style",
        "opacity",
        "marker-start",
        "marker-end",
        "id",
        "dx",
        "dy",
        "refX",
        "refY",
        "markerWidth",
        "markerHeight",
        "orient",
        "markerUnits",
        "baseline-shift",
        "preserveAspectRatio",
    }
)
# Colours come from the theme, so a drawing reads the same in light and dark mode.
THEME_CLASSES = frozenset(
    {
        "ink",
        "muted",
        "accent",
        "fill-ink",
        "fill-muted",
        "fill-accent",
        "fill-surface",
        "fill-canvas",
        "dashed",
        "thin",
        "thick",
        "small",
        "bold",
    }
)
PAINT = frozenset({"none", "currentColor"})
LOCAL_REFERENCE = re.compile(r"url\(#[A-Za-z][\w-]{0,40}\)\Z")
NUMBERS = re.compile(r"-?\d+(?:\.\d+)?")
PATH_TOKENS = re.compile(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
TRANSLATE = re.compile(r"\s*translate\(\s*(-?[\d.]+)(?:[\s,]+(-?[\d.]+))?\s*\)\s*\Z")
# Labels stay this far from any stroke; a label on or between lines is hard to read.
CLEARANCE = 5.0
# A conservative average glyph width for the app's sans-serif face, in em.
GLYPH_EM = {False: 0.6, True: 0.64}
SOLID = frozenset({"fill-ink", "fill-muted", "fill-accent"})
Box = tuple[float, float, float, float]
Point = tuple[float, float]


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def safe_svg(markup: str) -> str:
    """Accept a self-contained drawing; reject anything that could run, load or restyle."""
    if "<!" in markup or "<?" in markup:
        raise ValueError("A figure's SVG has no declarations, comments or processing instructions.")
    try:
        root = fromstring(markup)
    except (ParseError, DefusedXmlException):
        raise ValueError("A figure's SVG must be well-formed XML.") from None
    box = NUMBERS.findall(root.get("viewBox", ""))
    if _local(root.tag) != "svg" or len(box) != 4:
        raise ValueError("A figure's SVG starts with <svg> and gives a viewBox.")
    if not 160 <= float(box[2]) <= 480:
        raise ValueError("Draw a figure 160 to 480 units wide, so its labels stay readable.")
    elements = list(root.iter())
    if len(elements) > 400:
        raise ValueError("Keep a figure to at most 400 SVG elements.")
    for element in elements:
        tag = _local(element.tag)
        if tag not in SVG_ELEMENTS:
            raise ValueError(f"A figure's SVG may not use <{tag}>.")
        for raw, value in element.attrib.items():
            name = _local(raw)
            if name not in SVG_ATTRIBUTES:
                raise ValueError(f"A figure's SVG may not use the attribute {name}.")
            size = NUMBERS.match(value) if name == "font-size" else None
            if name == "font-size" and (size is None or float(size[0]) < 14):
                raise ValueError("Label text in a figure is at least 14 units.")
            if name in {"fill", "stroke"} and value not in PAINT:
                raise ValueError(
                    "Colour a figure with theme classes; fill and stroke take none or currentColor."
                )
            if name in {"marker-start", "marker-end"} and not LOCAL_REFERENCE.fullmatch(value):
                raise ValueError("A marker refers to a marker inside the same figure.")
            if name == "class" and not set(value.split()) <= THEME_CLASSES:
                raise ValueError(
                    "A figure uses only the theme classes: "
                    + ", ".join(sorted(THEME_CLASSES))
                    + "."
                )
    clashes = label_clashes(root, tuple(float(value) for value in box))
    if clashes:
        raise ValueError(
            "; ".join(clashes[:3])
            + f". Keep each label {CLEARANCE:g} units clear of lines, shapes and other labels."
        )
    return markup


def label_clashes(root: Element, view: tuple[float, ...]) -> list[str]:
    """Labels that touch a stroke, sit on a solid shape, overlap a label or leave the canvas.

    Label boxes are estimated from position, anchor and size, and shapes are flattened to
    segments, so the check runs the same way in a fresh install, in CI and at build time.
    """
    labels: list[tuple[str, Box]] = []
    strokes: list[tuple[str, list[Point]]] = []
    solids: list[tuple[str, float, float, float]] = []
    for element, (dx, dy), size, bold in _painted(root, (0.0, 0.0), 16.0, False):
        tag = _local(element.tag)
        if tag == "text":
            text = "".join(element.itertext()).strip()
            if text:
                labels.append((text, _label_box(element, text, dx, dy, size, bold)))
            continue
        classes = set(element.get("class", "").split())
        outline = [(x + dx, y + dy) for x, y in _outline(element, tag)]
        if len(outline) > 1 and element.get("stroke") != "none":
            strokes.append((tag, outline))
        if tag == "circle" and classes & SOLID:
            solids.append(
                (
                    tag,
                    _number(element, "cx") + dx,
                    _number(element, "cy") + dy,
                    _number(element, "r"),
                )
            )
    left, top, width, height = view
    clashes: list[str] = []
    for index, (text, (x0, y0, x1, y1)) in enumerate(labels):
        if x0 < left or y0 < top or x1 > left + width or y1 > top + height:
            clashes.append(f'Label "{text}" runs outside the canvas')
        padded = (x0 - CLEARANCE, y0 - CLEARANCE, x1 + CLEARANCE, y1 + CLEARANCE)
        for tag, points in strokes:
            if any(_segment_hits(a, b, padded) for a, b in zip(points, points[1:], strict=False)):
                clashes.append(f'Label "{text}" touches a <{tag}>')
                break
        for tag, cx, cy, r in solids:
            nearest_x, nearest_y = min(max(cx, x0), x1), min(max(cy, y0), y1)
            if math.hypot(cx - nearest_x, cy - nearest_y) < r + CLEARANCE:
                clashes.append(f'Label "{text}" sits on a filled <{tag}>')
                break
        for other, (u0, v0, u1, v1) in labels[index + 1 :]:
            if x0 < u1 and u0 < x1 and y0 < v1 and v0 < y1:
                clashes.append(f'Labels "{text}" and "{other}" overlap')
    return clashes


def _painted(
    element: Element, offset: Point, size: float, bold: bool
) -> Iterator[tuple[Element, Point, float, bool]]:
    """Painted elements with their translation and text style; skips defs and markers."""
    tag = _local(element.tag)
    if tag in {"defs", "marker", "title"}:
        return
    transform = element.get("transform")
    if transform:
        moved = TRANSLATE.match(transform)
        if moved is None:
            return  # rotated or scaled parts are checked by eye
        offset = (offset[0] + float(moved[1]), offset[1] + float(moved[2] or 0))
    classes = element.get("class", "").split()
    sized = NUMBERS.match(element.get("font-size", ""))
    size = float(sized[0]) if sized else 14.0 if "small" in classes else size
    bold = (
        bold or "bold" in classes or element.get("font-weight", "") in {"bold", "600", "650", "700"}
    )
    if tag != "svg":
        yield element, offset, size, bold
    if tag == "text":
        return
    for child in element:
        yield from _painted(child, offset, size, bold)


def _number(element: Element, name: str) -> float:
    found = NUMBERS.match(element.get(name, "0"))
    return float(found[0]) if found else 0.0


def _label_box(element: Element, text: str, dx: float, dy: float, size: float, bold: bool) -> Box:
    x = _number(element, "x") + _number(element, "dx") + dx
    y = _number(element, "y") + _number(element, "dy") + dy
    width = len(text) * size * GLYPH_EM[bold]
    start = {"middle": x - width / 2, "end": x - width}.get(element.get("text-anchor", ""), x)
    if element.get("dominant-baseline", "") in {"middle", "central"}:
        return (start, y - 0.45 * size, start + width, y + 0.45 * size)
    return (start, y - 0.72 * size, start + width, y + 0.22 * size)


def _outline(element: Element, tag: str) -> list[Point]:
    """A shape's stroke as a polyline."""
    match tag:
        case "line":
            return [
                (_number(element, "x1"), _number(element, "y1")),
                (_number(element, "x2"), _number(element, "y2")),
            ]
        case "rect":
            x, y = _number(element, "x"), _number(element, "y")
            w, h = _number(element, "width"), _number(element, "height")
            return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
        case "circle" | "ellipse":
            cx, cy = _number(element, "cx"), _number(element, "cy")
            rx = _number(element, "r") or _number(element, "rx")
            ry = _number(element, "r") or _number(element, "ry")
            steps = [2 * math.pi * k / 72 for k in range(73)]
            return [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in steps]
        case "polyline" | "polygon":
            values = [float(v) for v in NUMBERS.findall(element.get("points", ""))]
            points = list(zip(values[::2], values[1::2], strict=False))
            return points + points[:1] if tag == "polygon" else points
        case "path":
            return _path_points(element.get("d", ""))
        case _:
            return []


def _path_points(d: str) -> list[Point]:
    """Flatten path data; separate subpaths are joined only through their own points."""
    tokens = PATH_TOKENS.findall(d)
    points: list[Point] = []
    x = y = start_x = start_y = 0.0
    command = ""
    index = 0

    def take(count: int) -> list[float]:
        nonlocal index
        values = [float(v) for v in tokens[index : index + count]]
        index += count
        return values

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command in "Zz":
                x, y = start_x, start_y
                points.append((x, y))
                continue
        relative = command.islower()
        base_x, base_y = (x, y) if relative else (0.0, 0.0)
        match command.upper():
            case "M" | "L" | "T":
                px, py = take(2)
                x, y = base_x + px, base_y + py
                if command.upper() == "M":
                    if points:
                        points.append((math.nan, math.nan))
                    start_x, start_y = x, y
                    command = "l" if relative else "L"
                points.append((x, y))
            case "H":
                x = base_x + take(1)[0]
                points.append((x, y))
            case "V":
                y = (y if relative else 0.0) + take(1)[0]
                points.append((x, y))
            case "C" | "S" | "Q":
                count = {"C": 6, "S": 4, "Q": 4}[command.upper()]
                values = take(count)
                controls = [
                    (base_x + values[k], base_y + values[k + 1]) for k in range(0, count, 2)
                ]
                curve = [(x, y), *controls]
                for step in range(1, 17):
                    points.append(_bezier(curve, step / 16))
                x, y = controls[-1]
            case "A":
                rx, ry, angle, large, sweep, px, py = take(7)
                end = (base_x + px, base_y + py)
                points.extend(_arc((x, y), end, abs(rx), abs(ry), angle, bool(large), bool(sweep)))
                x, y = end
            case _:
                index += 1
    return points


def _bezier(points: list[Point], t: float) -> Point:
    while len(points) > 1:
        points = [
            (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            for a, b in zip(points, points[1:], strict=False)
        ]
    return points[0]


def _arc(
    start: Point, end: Point, rx: float, ry: float, angle: float, large: bool, sweep: bool
) -> list[Point]:
    """Sample an SVG elliptical arc (endpoint parameterisation, SVG 1.1 F.6.5)."""
    if rx == 0 or ry == 0:
        return [end]
    phi = math.radians(angle)
    cos, sin = math.cos(phi), math.sin(phi)
    hx, hy = (start[0] - end[0]) / 2, (start[1] - end[1]) / 2
    x1, y1 = cos * hx + sin * hy, -sin * hx + cos * hy
    scale = (x1 / rx) ** 2 + (y1 / ry) ** 2
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    numerator = max(rx**2 * ry**2 - rx**2 * y1**2 - ry**2 * x1**2, 0.0)
    factor = math.sqrt(numerator / (rx**2 * y1**2 + ry**2 * x1**2)) * (-1 if large == sweep else 1)
    cx1, cy1 = factor * rx * y1 / ry, -factor * ry * x1 / rx
    cx = cos * cx1 - sin * cy1 + (start[0] + end[0]) / 2
    cy = sin * cx1 + cos * cy1 + (start[1] + end[1]) / 2
    first = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    delta = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx) - first
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi
    samples = []
    for step in range(1, 33):
        t = first + delta * step / 32
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        samples.append((cos * ex - sin * ey + cx, sin * ex + cos * ey + cy))
    return samples


def _segment_hits(a: Point, b: Point, box: Box) -> bool:
    """Whether segment ab crosses the box (Liang-Barsky clipping)."""
    if math.isnan(a[0]) or math.isnan(b[0]):
        return False
    low, high = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in (
        (-dx, a[0] - box[0]),
        (dx, box[2] - a[0]),
        (-dy, a[1] - box[1]),
        (dy, box[3] - a[1]),
    ):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return False
    return True


def figure_bytes(path: Path) -> bytes:
    """An image a figure shows: present, confined to figures/, of its declared type and small."""
    extension = path.suffix.lstrip(".").lower()
    if not path.is_file() or path.is_symlink() or path.stat().st_size > IMAGE_BYTES:
        raise CampusError(
            Code.INVALID_RESPONSE,
            f"Figure image {path.name} is missing, linked or larger than 2 MB.",
        )
    payload = path.read_bytes()
    if not payload.startswith(SIGNATURES.get(extension, (b"\0invalid",))) or (
        extension == "webp" and payload[8:12] != b"WEBP"
    ):
        raise CampusError(
            Code.INVALID_RESPONSE, f"Figure image {path.name} is not the image type its name says."
        )
    return payload


def figure_images(value: JsonValue) -> Iterator[str]:
    """Every image file the built site's figures show, wherever the figure sits."""
    match value:
        case {"kind": "figure", "image": str() as image}:
            yield image
        case dict():
            for item in value.values():
                yield from figure_images(item)
        case list():
            for item in value:
                yield from figure_images(item)
        case _:
            return
