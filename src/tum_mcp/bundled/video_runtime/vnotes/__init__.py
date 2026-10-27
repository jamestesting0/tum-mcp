"""Scene helpers for Video Notes: beat timing, storyboard text and layout checks."""

import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from manim import (
    RIGHT,
    UP,
    MathTex,
    MathTypst,
    Mobject,
    Scene,
    SVGMobject,
    Typst,
    VectorizedPoint,
    VGroup,
    config,
)

from vnotes import style


class VideoNotesError(Exception):
    pass


@dataclass
class Context:
    storyboard: dict[str, Any]
    timing: dict[str, Any]
    style: dict[str, Any]
    fonts: Path
    assets: Path
    issues: list[dict[str, str]] = field(default_factory=list)


CONTEXT: Context | None = None


def configure(run: Path, fonts: Path) -> Context:
    global CONTEXT
    CONTEXT = Context(
        storyboard=json.loads((run / "storyboard.json").read_text(encoding="utf-8")),
        timing=json.loads((run / "timing.json").read_text(encoding="utf-8")),
        style=json.loads((run / "style.json").read_text(encoding="utf-8")),
        fonts=fonts,
        assets=run / "assets",
    )
    return CONTEXT


def _context() -> Context:
    if CONTEXT is None:
        raise VideoNotesError("Render scenes through tum-mcp video-notes render.")
    return CONTEXT


def _rows(glyphs: list[Mobject]) -> list[VGroup]:
    """Group glyph paths into text rows, top to bottom, by gaps in their vertical centres."""
    if not glyphs:
        return []
    ordered = sorted(glyphs, key=lambda glyph: -glyph.get_center()[1])
    heights = sorted(glyph.height for glyph in ordered)
    gap = 0.6 * heights[len(heights) // 2]
    rows = [[ordered[0]]]
    for glyph in ordered[1:]:
        if rows[-1][-1].get_center()[1] - glyph.get_center()[1] > gap:
            rows.append([])
        rows[-1].append(glyph)
    return [VGroup(*row) for row in rows]


def _typst_string(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'#"{escaped}"'


@dataclass
class BeatHandle:
    key: str
    duration: float
    started: float
    scene: "NotesScene"

    def share(self, fraction: float) -> float:
        if not 0 < fraction <= 1:
            raise VideoNotesError(f"{self.key}: share() takes a fraction in (0, 1].")
        return max(1 / config.frame_rate, self.duration * fraction)

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration - (self.scene.time - self.started))


class NotesScene(Scene):
    """Base class for one chapter. Class name C01 renders storyboard chapter c01."""

    def setup(self) -> None:
        context = _context()
        self.chapter_key = type(self).__name__.lower()
        chapters = {item["key"]: item for item in context.storyboard["chapters"]}
        if self.chapter_key not in chapters:
            raise VideoNotesError(f"{type(self).__name__} matches no storyboard chapter.")
        self.chapter = chapters[self.chapter_key]
        timings = {item["key"]: item for item in context.timing["beats"]}
        self.beat_order = [beat["key"] for beat in self.chapter["beats"]]
        self.beat_specs = {beat["key"]: beat for beat in self.chapter["beats"]}
        self.beat_timing = {key: timings[key] for key in self.beat_order}
        self.chapter_start = self.beat_timing[self.beat_order[0]]["start"]
        self.done: list[str] = []
        self.tokens = style.THEMES[context.style.get("theme", "dark")]
        self.screen = {
            item["key"]: item
            for chapter in context.storyboard["chapters"]
            for beat in chapter["beats"]
            for item in beat.get("on_screen", ())
        }
        self.camera.background_color = self.tokens["background"]

    def tear_down(self) -> None:
        missing = [key for key in self.beat_order if key not in self.done]
        if missing:
            raise VideoNotesError(f"{self.chapter_key}: beats never played: {', '.join(missing)}")

    def _frames(self, seconds: float) -> int:
        return round(seconds * config.frame_rate)

    @contextmanager
    def beat(self, key: str) -> Iterator[BeatHandle]:
        position = len(self.done)
        if position >= len(self.beat_order) or self.beat_order[position] != key:
            expected = self.beat_order[position] if position < len(self.beat_order) else "none"
            raise VideoNotesError(f"{self.chapter_key}: played beat {key}; expected {expected}.")
        timing = self.beat_timing[key]
        handle = BeatHandle(key=key, duration=timing["duration"], started=self.time, scene=self)
        yield handle
        target = self._frames(timing["start"] + timing["duration"]) - self._frames(
            self.chapter_start
        )
        current = self._frames(self.time)
        # One frame over is absorbed by the next beat's absolute target, never by the last.
        allowed = target if position == len(self.beat_order) - 1 else target + 1
        if current > allowed:
            over = (current - target) / config.frame_rate
            raise VideoNotesError(
                f"{key}: animations run {over:.2f}s past the narration; shorten run_time values."
            )
        if current < target:
            # A frozen wait renders int(duration * fps) frames; +0.5 makes that exactly n.
            self.wait((target - current + 0.5) / config.frame_rate, frozen_frame=True)
        self.done.append(key)
        self._probe(key)

    def _item(self, key: str, kind: str) -> dict[str, Any]:
        item = self.screen.get(key)
        if item is None or item["kind"] != kind:
            raise VideoNotesError(f"No storyboard on-screen {kind} named '{key}'.")
        return item

    def _mark(self, mobject: Mobject, key: str, kind: str, size: float) -> Mobject:
        mobject.vnotes_key = key
        mobject.vnotes_kind = kind
        mobject.vnotes_font = size
        mobject.vnotes_height = max(mobject.height, 1e-6)
        return mobject

    def _size(self, kind: str, size: float) -> float:
        if size < style.MIN_FONT[kind]:
            raise VideoNotesError(f"{kind} text below the {style.MIN_FONT[kind]} minimum size.")
        return size

    def _text_color(self, color: str | None) -> str:
        if color is None:
            return self.tokens["ink"]
        return self.color(color)

    def _typst(self, code: str, size: float, color: str) -> Typst:
        return Typst(
            code,
            font_size=size,
            color=color,
            typst_preamble='#set text(font: "Atkinson Hyperlegible Next")',
            font_paths=[str(_context().fonts)],
        )

    def label(self, key: str, *, size: float = 32, color: str | None = None) -> Mobject:
        item = self._item(key, "label")
        mobject = self._typst(
            _typst_string(item["text"]), self._size("label", size), self._text_color(color)
        )
        return self._mark(mobject, key, "label", size)

    def math(self, key: str, *, size: float = 40, color: str | None = None) -> Mobject:
        item = self._item(key, "math")
        size = self._size("math", size)
        if _context().style.get("math") == "latex" and item.get("source_latex"):
            mobject = MathTex(item["source_latex"], font_size=size, color=self._text_color(color))
        else:
            mobject = MathTypst(
                item["typst"],
                font_size=size,
                color=self._text_color(color),
                font_paths=[str(_context().fonts)],
            )
        return self._mark(mobject, key, "math", size)

    def number(self, key: str, *, size: float = 32, color: str | None = None) -> Mobject:
        item = self._item(key, "number")
        text = f"{item['value']:.{item.get('decimals', 0)}f}"
        if item.get("unit"):
            text = f"{text} {item['unit']}"
        mobject = self._typst(
            _typst_string(text), self._size("number", size), self._text_color(color)
        )
        return self._mark(mobject, key, "number", size)

    def value(self, key: str) -> float:
        return float(self._item(key, "number")["value"])

    def code(self, key: str, *, size: float = 24) -> VGroup:
        item = self._item(key, "code")
        size = self._size("code", size)
        language = item["language"].replace('"', "")
        rows = item["code"].split("\n")
        escaped = item["code"].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        # One raw block keeps indentation and blank lines; per-line renders drop both.
        block = self._typst(
            f'#raw("{escaped}", block: true, lang: "{language}")', size, self.tokens["ink"]
        )
        glyphs = [part for part in block.get_family() if part.has_points() and not part.submobjects]
        filled = [index for index, row in enumerate(rows) if row.strip()]
        groups = _rows(glyphs)
        if len(groups) != len(filled):
            raise VideoNotesError(f"Code item '{key}' could not be split into its lines.")
        centres = {row: group.get_center()[1] for row, group in zip(filled, groups, strict=True)}
        pitch = (
            (centres[filled[0]] - centres[filled[-1]]) / (filled[-1] - filled[0])
            if len(filled) > 1
            else block.height
        )
        lines = VGroup()
        groups_by_row = dict(zip(filled, groups, strict=True))
        for index in range(len(rows)):
            if index in groups_by_row:
                line = groups_by_row[index]
            else:
                anchor = max((row for row in filled if row < index), default=filled[0])
                y = centres[anchor] - (index - anchor) * pitch
                line = VGroup(VectorizedPoint(np.array([block.get_left()[0], y, 0])))
            line.vnotes_line = index + 1
            lines.add(line)
        return self._mark(lines, key, "code", size)

    def color(self, token: str) -> str:
        if token in self.tokens and isinstance(self.tokens[token], str):
            return self.tokens[token]
        if token.startswith("c") and token[1:].isdecimal():
            palette = self.tokens["palette"]
            index = int(token[1:]) - 1
            if 0 <= index < len(palette):
                return palette[index]
        raise VideoNotesError(f"Unknown color token '{token}'.")

    def symbol(self, name: str) -> str:
        return _context().style.get("symbol_colors", {}).get(name, self.tokens["ink"])

    def anchor(self, row: int, column: int) -> Any:
        x, y = style.anchor(row, column)
        return x * RIGHT + y * UP

    def region(self, name: str) -> tuple[float, float, float, float]:
        if name not in style.REGIONS:
            raise VideoNotesError(f"Unknown region '{name}'.")
        return style.REGIONS[name]

    def asset(self, name: str) -> SVGMobject:
        if "/" in name or "\\" in name or not name.endswith(".svg"):
            raise VideoNotesError("Assets are SVG files directly inside videos/assets/.")
        path = _context().assets / name
        if not path.is_file():
            raise VideoNotesError(f"Missing asset {name}.")
        return SVGMobject(str(path))

    def _visible(self, mobject: Mobject) -> bool:
        for part in mobject.get_family():
            try:
                if max(part.get_fill_opacity(), part.get_stroke_opacity()) > 0.05:
                    return True
            except (AttributeError, ValueError):
                continue
        return False

    def _texts(self) -> list[Mobject]:
        found: list[Mobject] = []

        def walk(mobject: Mobject) -> None:
            if getattr(mobject, "vnotes_key", None) is not None:
                if self._visible(mobject) and len(mobject.get_family()) > 0:
                    found.append(mobject)
                return
            for child in mobject.submobjects:
                walk(child)

        for mobject in self.mobjects:
            walk(mobject)
        return found

    def _probe(self, beat: str) -> None:
        context = _context()
        waived = self.beat_specs[beat].get("layout_waiver")
        left, right, bottom, top = style.safe_box()
        boxes = []
        for mobject in self._texts():
            box = (
                mobject.get_left()[0],
                mobject.get_right()[0],
                mobject.get_bottom()[1],
                mobject.get_top()[1],
            )
            boxes.append((mobject, box))
            name = getattr(mobject, "vnotes_key", "?")
            if box[0] < left - 1e-3 or box[1] > right + 1e-3 or box[3] > top + 1e-3:
                self._issue(context, beat, "layout.out_of_frame", name, waived)
            elif box[2] < bottom - 1e-3:
                self._issue(context, beat, "layout.caption_band", name, waived)
            scale = mobject.height / mobject.vnotes_height
            effective = mobject.vnotes_font * scale
            minimum = style.MIN_FONT[mobject.vnotes_kind] * 0.9
            if effective < minimum and not math.isclose(effective, minimum):
                self._issue(
                    context, beat, "layout.small_text", f"{name} at {effective:.0f}pt", waived
                )
        for index, (first, a) in enumerate(boxes):
            for second, b in boxes[index + 1 :]:
                width = min(a[1], b[1]) - max(a[0], b[0])
                height = min(a[3], b[3]) - max(a[2], b[2])
                if width <= 0 or height <= 0:
                    continue
                smaller = min((a[1] - a[0]) * (a[3] - a[2]), (b[1] - b[0]) * (b[3] - b[2]))
                if width * height > max(0.0025, 0.01 * smaller):
                    pair = f"{first.vnotes_key} x {second.vnotes_key}"
                    self._issue(context, beat, "layout.overlap", pair, waived)

    def _issue(self, context: Context, beat: str, rule: str, detail: str, waived: Any) -> None:
        context.issues.append(
            {
                "chapter": self.chapter_key,
                "beat": beat,
                "rule": rule + (".waived" if waived else ""),
                "detail": detail,
            }
        )


__all__ = ["NotesScene", "VideoNotesError"]
