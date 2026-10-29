"""Figures: SVG drawings checked against an allowlist, or images in the app's figures folder.

A figure shows what an idea looks like (an arm with its angles, a grid world, a circuit), so
authors may draw freely; the allowlist keeps scripts, links, external resources and fixed
colours out, and theme classes colour the drawing in light and dark mode.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from xml.etree.ElementTree import ParseError

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
NUMBERS = re.compile(r"-?\d+(\.\d+)?")


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
    if _local(root.tag) != "svg" or len(NUMBERS.findall(root.get("viewBox", ""))) != 4:
        raise ValueError("A figure's SVG starts with <svg> and gives a viewBox.")
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
    return markup


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
