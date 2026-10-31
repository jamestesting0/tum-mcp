"""Resolve fixed video colors from the bundled course app's explicit themes."""

import re
from pathlib import Path

from tum_mcp.errors import CampusError, Code
from tum_mcp.video_content import StyleProfile, canonical

STYLESHEET = Path(__file__).parent / "bundled/course_app/site/styles.css"
ROLE_TOKENS = {
    "background": "canvas",
    "ink": "ink",
    "muted": "muted",
    "line": "muted",
    "accent": "accent",
    "wash": "wash",
    "active": "accent",
    "active_ink": "canvas",
    "visited": "wash",
    "frontier": "accent",
    "emphasis": "accent",
    "positive": "tok-meta",
    "negative": "error",
}
PALETTE_TOKENS = ("accent", "tok-type", "tok-function", "tok-meta", "tok-keyword", "tok-string")


def _declarations(css: str, selector: str) -> dict[str, str]:
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^{}]*)\}", css)
    if match is None:
        raise CampusError(Code.INVALID_RESPONSE, f"App styles are missing selector {selector}.")
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", match[1]))


def resolve(style: StyleProfile, *, stylesheet: Path = STYLESHEET) -> dict:
    css = stylesheet.read_text(encoding="utf-8")
    declarations = _declarations(css, ":root")
    if style.theme == "dark":
        declarations.update(_declarations(css, ':root[data-theme="dark"]'))
    colors = {}
    for name in set(ROLE_TOKENS.values()) | set(PALETTE_TOKENS):
        value = declarations.get(name, "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
            raise CampusError(
                Code.INVALID_RESPONSE, f"App color --{name} must be a six-digit hex color."
            )
        colors[name] = value.upper()
    tokens = {role: colors[name] for role, name in ROLE_TOKENS.items()}
    tokens["palette"] = [colors[name] for name in PALETTE_TOKENS]
    for name, color in style.symbol_colors.items():
        if _contrast(color, colors["canvas"]) < 4.5:
            raise CampusError(
                Code.INVALID_RESPONSE,
                f"Symbol color '{name}' needs contrast of at least 4.5 "
                f"against {style.theme} canvas.",
            )
    return {
        **style.model_dump(mode="json"),
        "tokens": tokens,
        "token_sources": {**ROLE_TOKENS, "palette": list(PALETTE_TOKENS)},
    }


def staged_bytes(style: StyleProfile) -> bytes:
    return canonical(resolve(style))


def _contrast(first: str, second: str) -> float:
    # The isolated renderer keeps its own geometry/contrast helpers, without host imports.
    luminances = []
    for color in (first, second):
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        luminances.append(sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)))
    return (max(luminances) + 0.05) / (min(luminances) + 0.05)
