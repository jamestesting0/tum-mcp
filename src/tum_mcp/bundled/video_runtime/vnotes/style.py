"""Video Notes geometry and contrast helpers. Colors arrive in staged style.json."""

FRAME_WIDTH = 14.222222222222221
FRAME_HEIGHT = 8.0
SAFE_MARGIN = 0.3
CAPTION_BAND = 0.12 * FRAME_HEIGHT
GRID = 6

TEXT_TOKENS = ("ink", "muted", "accent", "emphasis", "positive", "negative", "frontier")
MIN_FONT = {"label": 24, "math": 30, "number": 24, "code": 20}
REGIONS = {
    "title": (-6.8, 6.8, 2.9, 3.7),
    "main": (-6.8, 6.8, -2.9, 2.8),
    "left": (-6.8, -0.3, -2.9, 2.8),
    "right": (0.3, 6.8, -2.9, 2.8),
    "note": (-6.8, 6.8, -3.0, -2.2),
}


def safe_box() -> tuple[float, float, float, float]:
    half_w, half_h = FRAME_WIDTH / 2, FRAME_HEIGHT / 2
    return (
        -half_w + SAFE_MARGIN,
        half_w - SAFE_MARGIN,
        -half_h + CAPTION_BAND,
        half_h - SAFE_MARGIN,
    )


def anchor(row: int, column: int) -> tuple[float, float]:
    if not (0 <= row < GRID and 0 <= column < GRID):
        raise ValueError(f"anchor({row}, {column}) is outside the {GRID}x{GRID} grid")
    left, right, bottom, top = safe_box()
    x = left + (column + 0.5) * (right - left) / GRID
    y = top - (row + 0.5) * (top - bottom) / GRID
    return round(x, 4), round(y, 4)


def luminance(color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(first: str, second: str) -> float:
    a, b = sorted((luminance(first), luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)
