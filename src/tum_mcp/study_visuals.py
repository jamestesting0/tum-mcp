"""Render check for a built study app: measure every painted visual and draw contact sheets.

Each unit's lesson and practice questions and each exercise step open in an installed Chromium
browser at phone, narrow and desktop width. A script measures what the app painted for each
visual; the findings go to ``.tum-mcp/visual-check.json``, tied to the content and app revision so
they go stale when either changes, and contact sheets of every visual at phone and desktop width
go to ``.tum-mcp/visuals/`` so the reviewing agent looks at what a student sees.
"""

import base64
import datetime
import hashlib
import html
import json
import math
import struct
from dataclasses import asdict, dataclass, field
from functools import partial
from importlib.resources import files
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any

from pydantic import JsonValue, TypeAdapter

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_store import private_path

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from tum_mcp.exam_content import ExamContent
    from tum_mcp.exercise_content import ExerciseContent
    from tum_mcp.study_content import Block, StudyContent

WIDTHS = {"phone": 390, "narrow": 600, "desktop": 1280}
SHEET_WIDTHS = ("phone", "desktop")
# CSS pixels of screenshots per contact-sheet page, so a page stays legible when viewed whole.
SHEET_HEIGHT = 1600
VISUAL_KINDS = frozenset({"diagram", "uml", "plot", "figure", "table"})
DEFECTS = frozenset(
    {
        "render_error",
        "fidelity",
        "edge_through_node",
        "coincident_edges",
        "label_overlap",
        "label_on_line",
        "label_on_node",
        "clipped_text",
        "tiny_text",
        "tall_cell",
        "table_scrolls",
        "tall_visual",
    }
)
# Waits for fonts and for every diagram layout, then two frames, without string evaluation in
# the page (the app's content security policy forbids it).
SETTLE = """async () => {
  await document.fonts.ready;
  const pending = () => document.querySelector('.uml-pending');
  if (pending()) await new Promise((resolve, reject) => {
    const observer = new MutationObserver(() => {
      if (!pending()) { clearTimeout(timer); observer.disconnect(); resolve(); }
    });
    const timer = setTimeout(() => {
      observer.disconnect(); reject(new Error('A diagram layout did not finish.'));
    }, 20000);
    const watch = { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] };
    observer.observe(document.body, watch);
  });
  await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
}"""
FRAMES = "() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))"
NOT_DRAWN = {"code": "fidelity", "detail": "the block was not drawn"}
# Loaded as a module script of the page: a dynamic import from an evaluated script fetches
# the app's modules again, and that fetch failed on Windows.
INJECTOR = "__visual-inject.mjs"
# A copy of a drawing that scrolls sideways, laid over the page at full size for its photograph.
UNROLL = """id => {
  const shot = document.querySelector(`[data-visual-shot="${CSS.escape(id)}"]`);
  const region = shot?.querySelector('.uml-region, .graph-region');
  const drawing = region?.querySelector('svg');
  if (!drawing) return false;
  const copy = document.createElement('div');
  copy.id = 'visual-unrolled'; copy.className = region.className;
  copy.style.cssText = 'position:absolute;left:0;top:0;z-index:2147483647;width:max-content;'
    + 'max-width:none;overflow:visible;background:var(--canvas)';
  copy.append(drawing.cloneNode(true));
  document.body.append(copy);
  return true;
}"""


@dataclass(slots=True)
class Visit:
    item: str
    route: str
    step: str = ""
    expected: dict[str, JsonValue] = field(default_factory=dict)
    inject: list[dict[str, JsonValue]] = field(default_factory=list)


@dataclass(slots=True)
class Visual:
    id: str
    kind: str
    title: str
    widths: dict[str, dict[str, Any]] = field(default_factory=dict)


def report_path(root: Path) -> Path:
    return private_path(root, "visual-check.json")


def _revision(item: Any) -> str:
    from tum_mcp.study_review import revision

    return revision(item)


def _visuals(blocks: "tuple[Block, ...]", prefix: str) -> dict[str, JsonValue]:
    from tum_mcp.study_content import render_blocks

    return {
        f"{prefix}:{index}": render_blocks((block,))[0]
        for index, block in enumerate(blocks)
        if block.kind in VISUAL_KINDS
    }


def _exam_visuals(exam: "ExamContent") -> dict[str, "Block"]:
    """Every visual block of Exam Prep, keyed by where it sits (concepts/heaps/details/0)."""
    from pydantic import BaseModel

    from tum_mcp.study_content import DiagramBlock, FigureBlock, PlotBlock, TableBlock, UmlBlock

    found: dict[str, Block] = {}

    def walk(value: object, path: str) -> None:
        if isinstance(value, DiagramBlock | FigureBlock | PlotBlock | TableBlock | UmlBlock):
            found[f"exam:{path}"] = value
        elif isinstance(value, BaseModel):
            for name in type(value).model_fields:
                walk(getattr(value, name), f"{path}/{name}" if path else name)
        elif isinstance(value, tuple):
            for index, item in enumerate(value):
                name = getattr(item, "key", None)
                walk(item, f"{path}/{index if name is None else name}")

    walk(exam, "")
    return found


def _visits(
    content: "StudyContent | None",
    exercises: "ExerciseContent | None",
    exam: "ExamContent | None" = None,
    units: frozenset[str] = frozenset(),
    tasks: frozenset[str] = frozenset(),
    *,
    with_exam: bool = False,
) -> tuple[list[Visit], dict[str, str]]:
    """The page loads that show every visual of the selected items, and each item's revision."""
    from tum_mcp.study_content import render_blocks

    everything = not units and not tasks and not with_exam
    visits: list[Visit] = []
    revisions: dict[str, str] = {}
    for unit in content.units if content else ():
        if not (everything or unit.key in units):
            continue
        item, route = f"study/{unit.key}", f"#{unit.key}/content"
        lesson = _visuals(unit.blocks, "block")
        questions: list[dict[str, JsonValue]] = [
            {"id": key, "title": question.prompt, "block": block}
            for question in unit.questions
            for key, block in _visuals(question.blocks, f"question:{question.key}").items()
        ]
        if lesson:
            visits.append(Visit(item, route, expected=lesson))
        if questions:
            expected = {str(entry["id"]): entry["block"] for entry in questions}
            visits.append(Visit(item, route, expected=expected, inject=questions))
        if lesson or questions:
            revisions[item] = _revision(unit)
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            if not (everything or f"{group.key}/{exercise.key}" in tasks):
                continue
            item = f"exercises/{group.key}/{exercise.key}"
            statement = _visuals(exercise.statement, "statement")
            for step in exercise.steps:
                expected = _visuals(step.blocks, f"step:{step.key}")
                drawn = step.check is not None and step.check.kind in ("graph", "plot")
                if item not in revisions and statement:
                    expected |= statement
                if expected or drawn:
                    route = f"#exercises/{group.key}/{exercise.key}/{step.key}"
                    visits.append(Visit(item, route, step.key, expected))
                    revisions[item] = _revision(exercise)
    if exam is not None and (everything or with_exam) and (found := _exam_visuals(exam)):
        # Exam Prep shows its blocks across many views; they are drawn in a lesson's column.
        host = f"#{content.units[0].key}/content" if content and content.units else "#home"
        shown: list[dict[str, JsonValue]] = [
            {"id": key, "title": block.title, "block": render_blocks((block,))[0]}
            for key, block in found.items()
        ]
        expected = {str(entry["id"]): entry["block"] for entry in shown}
        visits.append(Visit("exam", host, expected=expected, inject=shown))
        revisions["exam"] = _revision(exam)
    return visits, revisions


def visual_ids(
    content: "StudyContent | None", exercises: "ExerciseContent | None"
) -> dict[str, list[str]]:
    """Each unit's and exercise's visuals, under the keys the contact sheets show."""
    ids: dict[str, list[str]] = {}
    for visit in _visits(content, exercises)[0]:
        keys = ids.setdefault(visit.item, [])
        keys.extend(key for key in visit.expected if key not in keys)
    return ids


def _gallery(route: str) -> list[Visit]:
    from tum_mcp.study_content import Block, render_blocks

    path = files("tum_mcp.bundled").joinpath("skills/review-course/references/visual-gallery.json")
    gallery = json.loads(path.read_text(encoding="utf-8"))
    adapter: TypeAdapter[Block] = TypeAdapter(Block)
    items: list[dict[str, JsonValue]] = [
        {
            "id": f"gallery:{entry['key']}",
            "title": entry["key"],
            "block": render_blocks((adapter.validate_python(entry["block"]),))[0],
        }
        for entry in gallery["items"]
    ]
    return [Visit("gallery", route, inject=items)]


def app_revision(site: Path) -> str:
    from tum_mcp.study_build import TEMPLATE_FILES

    digest = hashlib.sha256()
    for name in TEMPLATE_FILES:
        path = site / name
        if path.is_file():
            digest.update(name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:16]


def _sheets(page: "Page", shots: list[tuple[str, bytes]], width: int, stem: Path) -> list[Path]:
    pages: list[list[tuple[str, bytes]]] = [[]]
    used = 0
    for caption, image in shots:
        # PNG height sits in the IHDR chunk; screenshots are taken at twice the CSS size.
        height = struct.unpack(">I", image[20:24])[0] // 2 + 40
        if pages[-1] and used + height > SHEET_HEIGHT:
            pages.append([])
            used = 0
        pages[-1].append((caption, image))
        used += height
    for old in stem.parent.glob(f"{stem.name}-*.png"):
        old.unlink()
    written = []
    for number, chunk in enumerate(pages, 1):
        cells = "".join(
            f"<figure><figcaption>{html.escape(caption)}</figcaption>"
            f'<img src="data:image/png;base64,{base64.b64encode(image).decode()}"></figure>'
            for caption, image in chunk
        )
        page.set_content(
            "<!doctype html><style>body{margin:0;padding:12px;font:13px sans-serif;"
            f"background:#fff}}figure{{margin:0 0 16px;max-width:{width}px}}"
            "img{display:block;max-width:100%;border:1px solid #ccd}"
            "figcaption{color:#345;margin-bottom:4px}</style>" + cells
        )
        out = stem.parent / f"{stem.name}-{number}.png"
        page.screenshot(path=str(out), full_page=True)
        written.append(out)
    return written


def _open(page: "Page", url: str) -> None:
    page.goto(url)
    page.wait_for_load_state("networkidle")
    page.evaluate(SETTLE)


def _shoot(page: "Page", selector: str, width: int, *, widen: bool = False) -> bytes:
    """Photograph an element whole: the viewport grows to fit it, so nothing is cut off."""
    target = page.locator(selector).first
    box = target.bounding_box() or {"width": 0, "height": 0}
    size = {
        "width": max(width, math.ceil(box["width"]) + 16) if widen else width,
        "height": max(900, math.ceil(box["height"]) + 120),
    }
    if size != {"width": width, "height": 900}:
        page.set_viewport_size(size)
        page.evaluate(FRAMES)
    try:
        return target.screenshot()
    finally:
        if size != {"width": width, "height": 900}:
            page.set_viewport_size({"width": width, "height": 900})
            page.evaluate(FRAMES)


def _measure(
    root: Path, site: Path, visits: list[Visit], sheet_stem: str | None = None
) -> tuple[dict[str, dict[str, Visual]], dict[str, list[str]]]:
    from playwright.sync_api import sync_playwright

    from tum_mcp.moodle.browser_runtime import browser_driver
    from tum_mcp.moodle.browsers import discover_browsers
    from tum_mcp.study_preview import Handler, PreviewServer

    choices = discover_browsers()
    if not choices:
        raise CampusError(Code.ACTION_REQUIRED, "Install Chrome, Edge or Chromium for the check.")
    bundled = files("tum_mcp.bundled")
    measure = bundled.joinpath("visual_check.js").read_text(encoding="utf-8")
    inject = bundled.joinpath("visual_inject.js").read_text(encoding="utf-8")
    host = next((visit.route for visit in visits if visit.route.endswith("/content")), "#home")
    folder = root / ".tum-mcp" / "visuals"
    folder.mkdir(parents=True, exist_ok=True)
    measured: dict[str, dict[str, Visual]] = {}
    shots: dict[str, list[tuple[str, bytes]]] = {}
    sheets: dict[str, list[str]] = {}
    server = PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(site)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/"
    try:
        with browser_driver(choices[0]), sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=choices[0].executable)
            try:
                for name, pixels in WIDTHS.items():
                    photograph = name in SHEET_WIDTHS
                    context = browser.new_context(
                        viewport={"width": pixels, "height": 900},
                        device_scale_factor=2 if photograph else 1,
                    )
                    page = context.new_page()
                    # The injector is served by the browser itself, never written to the site.
                    page.route(
                        base + INJECTOR,
                        lambda route: route.fulfill(content_type="text/javascript", body=inject),
                    )
                    errors: list[str] = []
                    page.on("pageerror", lambda error, sink=errors: sink.append(str(error)))
                    shots.clear()
                    for visit in visits:
                        _open(page, base + (visit.route or host))
                        if visit.inject:
                            if not page.evaluate("() => Boolean(window.__visualInject)"):
                                page.add_script_tag(url=base + INJECTOR, type="module")
                            page.evaluate("items => window.__visualInject(items)", visit.inject)
                            page.evaluate(SETTLE)
                        found = page.evaluate(
                            measure, {"step": visit.step, "expected": visit.expected}
                        )
                        visuals = measured.setdefault(visit.item, {})
                        for entry in found:
                            visual = visuals.setdefault(
                                entry["id"], Visual(entry["id"], entry["kind"], entry["title"])
                            )
                            if name in visual.widths:
                                continue
                            visual.widths[name] = {
                                "findings": entry["findings"],
                                "facts": entry["facts"],
                            }
                            if photograph:
                                codes = sorted({finding["code"] for finding in entry["findings"]})
                                caption = " · ".join(
                                    [
                                        entry["title"],
                                        entry["id"],
                                        *([", ".join(codes)] if codes else []),
                                    ]
                                )
                                selector = f'[data-visual-shot="{entry["id"]}"]'
                                taken = shots.setdefault(visit.item, [])
                                taken.append((caption, _shoot(page, selector, pixels)))
                                if entry["facts"].get("scrolls") and page.evaluate(
                                    UNROLL, entry["id"]
                                ):
                                    whole = _shoot(page, "#visual-unrolled", pixels, widen=True)
                                    page.evaluate(
                                        "document.getElementById('visual-unrolled').remove()"
                                    )
                                    taken.append((f"{caption} · whole drawing", whole))
                        for key in visit.expected:
                            missing = visuals.setdefault(key, Visual(key, "missing", ""))
                            missing.widths.setdefault(name, {"findings": [NOT_DRAWN], "facts": {}})
                        if errors:
                            page_errors = visuals.setdefault("page", Visual("page", "page", ""))
                            page_errors.widths.setdefault(name, {"findings": [], "facts": {}})
                            page_errors.widths[name]["findings"] += [
                                {"code": "render_error", "detail": error} for error in errors
                            ]
                            errors.clear()
                    if photograph:
                        sheet_page = context.new_page()
                        for item, taken in shots.items():
                            stem = folder / f"{sheet_stem or item.replace('/', '_')}-{name}"
                            sheets.setdefault(item, []).extend(
                                str(path.relative_to(root))
                                for path in _sheets(sheet_page, taken, pixels, stem)
                            )
                    context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=3)
    return measured, sheets


def _defects(items: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"item": item, "visual": visual["id"], "title": visual["title"], "width": width, **finding}
        for item, record in items.items()
        for visual in record["visuals"]
        for width, measured in visual["widths"].items()
        for finding in measured["findings"]
        if finding["code"] in DEFECTS
    ]


def read_report(root: Path) -> dict[str, Any] | None:
    path = report_path(root)
    if not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        return None
    return report


def check_visuals(
    project: Path,
    units: tuple[str, ...] = (),
    exercises: tuple[str, ...] = (),
    *,
    exam: bool = False,
    gallery: bool = False,
) -> dict[str, Any]:
    from tum_mcp.exam_data import read_exam
    from tum_mcp.exercise_data import read_exercises
    from tum_mcp.study_build import read_content

    root = project.expanduser().resolve()
    site = app_path(root, "index.html").parent
    if not (site / "data.mjs").is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Build the study site first.")
    content = read_content(root) if app_path(root, "content.json").is_file() else None
    if gallery:
        # The gallery is drawn in a lesson's reading column, where real visuals appear.
        route = f"#{content.units[0].key}/content" if content and content.units else "#home"
        measured, sheets = _measure(root, site, _gallery(route), "gallery")
        return {
            "sheets": sheets.get("gallery", []),
            "findings": {
                visual.id: sorted(
                    {
                        f"{finding['code']} ({width})"
                        for width, entry in visual.widths.items()
                        for finding in entry["findings"]
                    }
                )
                for visual in measured.get("gallery", {}).values()
            },
        }
    visits, revisions = _visits(
        content,
        read_exercises(root),
        read_exam(root),
        frozenset(units),
        frozenset(exercises),
        with_exam=exam,
    )
    measured, sheets = _measure(root, site, visits) if visits else ({}, {})
    app = app_revision(site)
    previous = read_report(root)
    items: dict[str, Any] = dict(previous["items"]) if previous and previous["app"] == app else {}
    today = datetime.date.today().isoformat()
    for item, value in revisions.items():
        items[item] = {
            "revision": value,
            "checked_at": today,
            "visuals": [asdict(visual) for visual in measured.get(item, {}).values()],
            "sheets": sheets.get(item, []),
        }
    report_path(root).write_text(
        json.dumps({"schema_version": 1, "app": app, "items": items}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    checked = {item: items[item] for item in revisions}
    defects = _defects(checked)
    selected = {item.split("/", 1)[1] for item in revisions if item.startswith("study/")}
    return {
        "passed": not defects,
        "checked": sorted(revisions),
        "defects": defects,
        "sheets": sorted(sheet for record in checked.values() for sheet in record["sheets"]),
        **({"no_visuals": sorted(set(units) - selected)} if set(units) - selected else {}),
    }


def render_report(
    root: Path,
    content: "StudyContent | None",
    exercises: "ExerciseContent | None",
    exam: "ExamContent | None" = None,
) -> dict[str, JsonValue]:
    """Which items with visuals lack a current render check, and what the last check found."""
    _, revisions = _visits(content, exercises, exam)
    report = read_report(root)
    site = app_path(root, "index.html").parent
    app = app_revision(site) if (site / "data.mjs").is_file() else None
    stored: dict[str, Any] = report["items"] if report else {}
    fresh = report is not None and report["app"] == app
    unchecked = sorted(item for item in revisions if item not in stored)
    stale = sorted(
        item
        for item in revisions
        if item in stored and (not fresh or stored[item]["revision"] != revisions[item])
    )
    current = {item: stored[item] for item in revisions if item in stored and item not in stale}
    defects = _defects(current)
    return {
        "checked": report is not None,
        "passed": not (unchecked or stale or defects),
        "unchecked": list(unchecked),
        "stale": list(stale),
        "defects": defects,
    }
