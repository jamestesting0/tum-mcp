"""Render check for a built study app: measure every painted visual and draw contact sheets.

Each unit's lesson and practice questions and each exercise step open in an installed Chromium
browser at desktop width, and with ``phone`` also at phone and narrow width. A script measures
what the app painted for each visual; the findings go to ``.tum-mcp/visual-check.json``, tied to
the content and app revision so they go stale when either changes, and contact sheets of every
visual at each checked width (phone and desktop, not narrow) go to ``.tum-mcp/visuals/`` so the
reviewing agent looks at what a student sees.
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

from filelock import FileLock
from pydantic import JsonValue, TypeAdapter

from tum_mcp.course.app.browser_evidence import (
    browser_choice,
    browser_identity,
    cached,
    result_key,
    reusable,
    save_receipt,
)
from tum_mcp.course.content.store import present
from tum_mcp.course.project.paths import app_path
from tum_mcp.course.project.store import private_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from tum_mcp.course.content.exam import ExamContent
    from tum_mcp.course.content.exercises import ExerciseContent
    from tum_mcp.course.content.study import Block, StudyContent
    from tum_mcp.moodle.browsers import BrowserChoice

WIDTHS = {"phone": 390, "narrow": 600, "desktop": 1280}
# Desktop is checked by default; phone and narrow widths only when asked (`--phone`).
DEFAULT_WIDTHS = ("desktop",)
SHEET_WIDTHS = ("phone", "desktop")
# A visual present in the page but not shown at a width (a collapsed step, a closed panel).
HIDDEN = {"code": "not_shown", "detail": "present but not shown at this width; not photographed"}
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
    from tum_mcp.course.review.models import revision

    return revision(item)


def _visuals(blocks: "tuple[Block, ...]", prefix: str) -> dict[str, JsonValue]:
    from tum_mcp.course.content.study import render_blocks

    return {
        f"{prefix}:{index}": render_blocks((block,))[0]
        for index, block in enumerate(blocks)
        if drawn(block)
    }


def drawn(block: "Block") -> bool:
    """A block the check measures: a drawn visual, or a walkthrough over one."""
    stage = getattr(block, "stage", None)
    return block.kind in VISUAL_KINDS or (stage is not None and stage.kind in VISUAL_KINDS)


def _exam_visuals(exam: "ExamContent") -> dict[str, "Block"]:
    """Every visual block of Exam, keyed by where it sits (concepts/heaps/details/0)."""
    from pydantic import BaseModel

    from tum_mcp.course.content.study import (
        DiagramBlock,
        FigureBlock,
        PlotBlock,
        TableBlock,
        UmlBlock,
        WalkthroughBlock,
    )

    found: dict[str, Block] = {}

    def walk(value: object, path: str) -> None:
        if isinstance(value, DiagramBlock | FigureBlock | PlotBlock | TableBlock | UmlBlock) or (
            isinstance(value, WalkthroughBlock) and drawn(value)
        ):
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
    from tum_mcp.course.content.responses import SelfCheck
    from tum_mcp.course.content.study import render_blocks

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
        optional = {
            key: block
            for material in unit.explore
            for key, block in _visuals(material.blocks, f"explore:{material.key}").items()
        }
        if optional:
            visits.append(Visit(item, f"#{unit.key}/explore", expected=optional))
        if lesson or questions or optional:
            revisions[item] = _revision(unit)
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            if not (everything or f"{group.key}/{exercise.key}" in tasks):
                continue
            item = f"exercises/{group.key}/{exercise.key}"
            statement = _visuals(exercise.statement, "statement")
            answers = _visuals(exercise.solution.blocks, "solution")
            if exercise.transfer:
                answers |= _visuals(exercise.transfer.answer, "transfer")
            for step in exercise.steps:
                match step.check:
                    case SelfCheck(model_answer=tuple(blocks)):
                        answers |= _visuals(blocks, f"compare:{step.key}")
                expected = _visuals(step.blocks, f"step:{step.key}")
                drawn = step.check is not None and step.check.kind in ("graph", "plot")
                if item not in revisions and statement:
                    expected |= statement
                if expected or drawn:
                    route = f"#exercises/{group.key}/{exercise.key}/{step.key}"
                    visits.append(Visit(item, route, step.key, expected))
                    revisions[item] = _revision(exercise)
            if answers:
                route = f"#exercises/{group.key}/{exercise.key}"
                shown = [
                    {"id": key, "title": key, "block": block} for key, block in answers.items()
                ]
                visits.append(Visit(item, route, expected=answers, inject=shown))
                revisions[item] = _revision(exercise)
    if exam is not None and (everything or with_exam) and (found := _exam_visuals(exam)):
        # Exam shows its blocks across many views; they are drawn in a lesson's column.
        host = f"#{content.units[0].key}/content" if content and content.units else "#home"
        shown: list[dict[str, JsonValue]] = [
            {"id": key, "title": block.title or key, "block": render_blocks((block,))[0]}
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
    from tum_mcp.course.content.study import Block, render_blocks

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
    from tum_mcp.course.app.build import TEMPLATE_FILES

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
    page.locator("#app > .shell").wait_for(state="attached")
    page.evaluate(SETTLE)


def _shoot(page: "Page", selector: str, width: int, *, widen: bool = False) -> bytes | None:
    """Photograph an element whole: the viewport grows to fit it, so nothing is cut off.
    An element the page does not show at this width has nothing to photograph."""
    target = page.locator(selector).first
    box = target.bounding_box()
    if box is None or not target.is_visible():
        return None
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
    root: Path,
    site: Path,
    visits: list[Visit],
    sheet_stem: str | None = None,
    widths: tuple[str, ...] = tuple(WIDTHS),
    *,
    choice: "BrowserChoice | None" = None,
    stamp: str = "",
) -> tuple[dict[str, dict[str, Visual]], dict[tuple[str, str], tuple[str, ...]]]:
    from playwright.sync_api import sync_playwright

    from tum_mcp.course.app.preview import Handler, PreviewServer
    from tum_mcp.moodle.browser_runtime import browser_driver, launch_loopback_browser

    choice = choice or browser_choice()
    bundled = files("tum_mcp.bundled")
    measure = bundled.joinpath("visual_check.js").read_text(encoding="utf-8")
    inject = bundled.joinpath("visual_inject.js").read_text(encoding="utf-8")
    host = next((visit.route for visit in visits if visit.route.endswith("/content")), "#home")
    folder = root / ".tum-mcp" / "visuals" / stamp
    folder.mkdir(parents=True, exist_ok=True)
    measured: dict[str, dict[str, Visual]] = {}
    shots: dict[str, list[tuple[str, bytes]]] = {}
    sheets: dict[tuple[str, str], tuple[str, ...]] = {}
    server = PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(site)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/"
    try:
        with browser_driver(choice), sync_playwright() as playwright:
            browser = launch_loopback_browser(playwright.chromium, choice)
            try:
                for name, pixels in ((name, WIDTHS[name]) for name in widths):
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
                                shot = _shoot(page, selector, pixels)
                                if shot is None:
                                    visual.widths[name]["findings"].append(HIDDEN)
                                    continue
                                taken.append((caption, shot))
                                if entry["facts"].get("scrolls") and page.evaluate(
                                    UNROLL, entry["id"]
                                ):
                                    whole = _shoot(page, "#visual-unrolled", pixels, widen=True)
                                    page.evaluate(
                                        "document.getElementById('visual-unrolled').remove()"
                                    )
                                    if whole is not None:
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
                            sheets[item, name] = tuple(
                                path.relative_to(root).as_posix()
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
    if not isinstance(report.get("items"), dict) or not isinstance(report.get("app"), str):
        return None
    return report


def check_visuals(
    project: Path,
    units: tuple[str, ...] = (),
    exercises: tuple[str, ...] = (),
    *,
    exam: bool = False,
    gallery: bool = False,
    phone: bool = False,
) -> dict[str, Any]:
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.content.exam_data import read_exam
    from tum_mcp.course.content.exercise_data import read_exercises

    root = project.expanduser().resolve()
    site = app_path(root, "index.html").parent
    if not (site / "data.mjs").is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Build the study site first.")
    content = read_content(root) if present(root, "study") else None
    if gallery:
        # The gallery is drawn in a lesson's reading column, where real visuals appear.
        route = f"#{content.units[0].key}/content" if content and content.units else "#home"
        measured, sheets = _measure(root, site, _gallery(route), "gallery")
        return {
            "sheets": [path for paths in sheets.values() for path in paths],
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
    widths = tuple(WIDTHS) if phone else DEFAULT_WIDTHS
    choice = browser_choice()
    identity = browser_identity(root, choice)
    request = result_key("visual", [*revisions, *units, *exercises], widths)
    required = tuple(f"visual/{width}/{item}" for width in widths for item in revisions)
    if previous_result := cached(root, identity, request, required):
        return previous_result
    keyed = {
        f"visual/{width}/{item}": value for width in widths for item, value in revisions.items()
    }
    kept = reusable(root, identity, keyed)
    unchanged = {
        item for item in revisions if all(f"visual/{width}/{item}" in kept for width in widths)
    }
    fresh = [visit for visit in visits if visit.item not in unchanged]
    measured, sheets = (
        _measure(root, site, fresh, widths=widths, choice=choice, stamp=identity.build)
        if fresh
        else ({}, {})
    )
    items = {
        item: {
            "revision": value,
            "checked_at": datetime.date.today().isoformat(),
            "visuals": [asdict(visual) for visual in measured.get(item, {}).values()],
            "sheets": [path for width in widths for path in sheets.get((item, width), ())],
        }
        for item, value in revisions.items()
        if item not in unchanged
    }
    defects = _defects(items)
    failed = {(defect["item"], defect["width"]) for defect in defects}
    states = {
        f"visual/{width}/{item}": item in unchanged or (item, width) not in failed
        for width in widths
        for item in revisions
    }
    selected = {item.split("/", 1)[1] for item in revisions if item.startswith("study/")}
    result = {
        "passed": not defects,
        "checked": sorted(revisions),
        **({"unchanged": sorted(unchanged)} if unchanged else {}),
        "defects": defects,
        "sheets": sorted(sheet for record in items.values() for sheet in record["sheets"]),
        **({"no_visuals": sorted(set(units) - selected)} if set(units) - selected else {}),
    }
    save_receipt(
        root,
        identity,
        states,
        (request, result),
        captures={f"visual/{width}/{item}": paths for (item, width), paths in sheets.items()}
        | {
            f"visual/{width}/{item}": kept[f"visual/{width}/{item}"]
            for width in widths
            for item in unchanged
        },
        revisions=keyed,
    )
    with FileLock(str(private_path(root, "update.lock"))):
        app = app_revision(site)
        previous = read_report(root)
        existing = (
            previous["items"]
            if previous and previous["app"] == app
            else {
                item: record
                for item, record in (previous["items"] if previous else {}).items()
                if item in unchanged and record.get("revision") == revisions[item]
            }
        )
        private_write(
            report_path(root),
            (
                json.dumps(
                    {"schema_version": 1, "app": app, "items": existing | items},
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode(),
        )
    return result


def interaction_routes(
    content: "StudyContent | None",
    exercises: "ExerciseContent | None",
) -> dict[str, str]:
    """Stable review item IDs to their normal interactive routes."""
    return {
        **{
            f"study/{unit.key}": f"#{unit.key}/content"
            for unit in (content.units if content else ())
        },
        **{
            f"exercises/{group.key}/{exercise.key}": f"#exercises/{group.key}/{exercise.key}"
            for group in (exercises.sets if exercises else ())
            for exercise in group.exercises
        },
    }


def shell_workspace(route: str) -> str:
    return "study" if route.endswith("/content") else route.lstrip("#").split("/", 1)[0]


def shell_routes(routes: list[str]) -> list[str]:
    by_workspace: dict[str, str] = {}
    for route in routes:
        by_workspace.setdefault(shell_workspace(route), route)
    return list(by_workspace.values())


def _outline(page: "Page", width: str) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if width != "desktop":
        page.locator(".outline-toggle").click()
    body = page.locator(".sidebar-body")
    links = body.locator("a.unit-link:not(.revision-link)")
    link = links.filter(has=page.locator(".unit-title")).first
    if link.is_visible():
        before = link.bounding_box()
        link.click(button="right")
        action = page.get_by_role("menuitem", name="Mark as completed", exact=True)
        action.click()
        after = link.bounding_box()
        mark = link.locator(".done-mark svg").bounding_box()
        title = link.locator(".unit-title").bounding_box()
        if (
            not before
            or not after
            or not mark
            or not title
            or abs(mark["y"] - title["y"]) > 6
            or abs(before["height"] - after["height"]) > 1
        ):
            problems.append(
                {
                    "control": "outline",
                    "problem": "Completion changed the row or left the first line.",
                }
            )
        link.focus()
        page.keyboard.press("Shift+F10")
        page.get_by_role("menuitem", name="Mark as not completed", exact=True).press("Enter")
    intact = body.evaluate("""body => {
      const main = document.querySelector('main'), before = main.scrollTop;
      body.scrollTop = body.scrollHeight;
      return body.scrollWidth <= body.clientWidth + 1 && main.scrollTop === before;
    }""")
    if not intact:
        problems.append(
            {
                "control": "outline",
                "problem": "Outline scroll moved the reading pane or overflowed horizontally.",
            }
        )
    return problems


def check_interactions(
    project: Path,
    units: tuple[str, ...] = (),
    exercises: tuple[str, ...] = (),
    *,
    exam: bool = False,
    phone: bool = False,
) -> dict[str, Any]:
    """Exercise the applicable student routes and preserve exact-build receipts."""
    from playwright.sync_api import Error as BrowserError
    from playwright.sync_api import sync_playwright

    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.app.preview import Handler, PreviewServer
    from tum_mcp.course.content.exam_data import read_exam
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.lecture.data import read_lectures
    from tum_mcp.moodle.browser_runtime import browser_driver, launch_loopback_browser

    root = project.expanduser().resolve()
    site = app_path(root, "index.html").parent
    choice = browser_choice()
    identity = browser_identity(root, choice)
    content = read_content(root) if present(root, "study") else None
    candidates = interaction_routes(content, read_exercises(root))
    selected = [*(f"study/{key}" for key in units), *(f"exercises/{key}" for key in exercises)]
    if missing := set(selected) - candidates.keys():
        raise CampusError(
            Code.ACTION_REQUIRED, "Unknown browser items: " + ", ".join(sorted(missing))
        )
    everything = not (selected or exam)
    routes = [route for key, route in candidates.items() if everything or key in selected]
    exam_content = read_exam(root) if everything or exam else None
    if exam_content:
        routes += ["#exam", "#exam/sheet"]
        routes += [f"#exam/patterns/{pattern.key}" for pattern in exam_content.patterns]
        routes += [f"#exam/mock/{mock.key}" for mock in exam_content.mocks]
        routes += [
            f"#exam/paper/{variant.key}/exam"
            for sitting in exam_content.sittings
            for variant in sitting.variants
            if variant.replayable
        ]
    lectures = read_lectures(root) if everything else None
    routes += [f"#lectures/{lecture.key}" for lecture in (lectures.lectures if lectures else ())]
    widths = tuple(WIDTHS) if phone else DEFAULT_WIDTHS
    request = result_key("interact", routes, widths)
    required = (
        *(f"interact/{width}/{route}" for width in widths for route in routes),
        *(
            f"shell/{width}/{theme}/{shell_workspace(route)}"
            for width in widths
            for theme in ("light", "dark")
            for route in shell_routes(routes)
        ),
    )
    if previous_result := cached(root, identity, request, required):
        return previous_result
    query = content.units[0].title.split()[0] if content else ""
    script = files("tum_mcp.bundled").joinpath("interaction_check.js").read_text(encoding="utf-8")
    problems: list[dict[str, str]] = []
    states: dict[str, bool] = {}
    used = 0
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(site))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}/"
        try:
            with browser_driver(choice), sync_playwright() as playwright:
                browser = launch_loopback_browser(playwright.chromium, choice)
                try:
                    for width in widths:
                        with browser.new_context(
                            viewport={"width": WIDTHS[width], "height": 900},
                            color_scheme="light",
                            reduced_motion="reduce",
                        ) as context:
                            page = context.new_page()
                            errors: list[str] = []
                            page.on("pageerror", lambda error, sink=errors: sink.append(str(error)))
                            for index, route in enumerate(routes):
                                try:
                                    _open(page, base + route)
                                    found = page.evaluate(
                                        script,
                                        {
                                            "query": query if index == 0 else "",
                                            "study": route[1:].split("/")[0]
                                            if route.endswith("/content")
                                            else None,
                                            "exercise": route.rsplit("/", 1)[-1]
                                            if route.startswith("#exercises/")
                                            else None,
                                        },
                                    )
                                    used += found["used"]
                                    issues = found["problems"]
                                except BrowserError as error:
                                    issues = [
                                        {"control": "page", "problem": str(error).splitlines()[0]}
                                    ]
                                issues += [
                                    {"control": "page", "problem": error} for error in errors
                                ]
                                states[f"interact/{width}/{route}"] = not issues
                                problems += [
                                    {"route": route, "width": width, **issue} for issue in issues
                                ]
                                errors.clear()
                        for theme in ("light", "dark"):
                            with browser.new_context(
                                viewport={"width": WIDTHS[width], "height": 620}, color_scheme=theme
                            ) as context:
                                page = context.new_page()
                                for route in shell_routes(routes):
                                    try:
                                        _open(page, base + route)
                                        issues = _outline(page, width)
                                    except BrowserError as error:
                                        issues = [
                                            {
                                                "control": "outline",
                                                "problem": str(error).splitlines()[0],
                                            }
                                        ]
                                    states[
                                        f"shell/{width}/{theme}/{shell_workspace(route)}"
                                    ] = not issues
                                    problems += [
                                        {"route": route, "width": width, "theme": theme, **issue}
                                        for issue in issues
                                    ]
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
    result = {"passed": not problems, "pages": len(routes), "controls": used, "problems": problems}
    save_receipt(root, identity, states, (request, result))
    return result


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
