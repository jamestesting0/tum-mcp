import os
import re
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser, expect
from playwright.sync_api import TimeoutError as BrowserTimeout
from pydantic import TypeAdapter
from study_browser_fixture import study_website

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def test_study_website_journeys_pass_in_the_checkout(course_browser: Browser) -> None:
    assert study_website(course_browser)["passed"]


TREE_WALKTHROUGH = """async () => {
    const { renderWalkthrough } = await import('./runtime/reading/walkthrough.mjs');
    const keys = 'abcdefghijklmno'.split('');
    const nodes = keys.map(key => ({ key, label: key.toUpperCase() }));
    const edges = keys.slice(1).map((key, index) =>
        ({ start: keys[Math.floor(index / 2)], end: key, directed: true }));
    const step = (shown, values, active) => ({ action: `Expand ${active}`, why: 'Deepest first.',
        active: [active], frontier: [], visited: [], edges: [], state: [],
        visible_nodes: shown, node_values: values });
    const stage = { kind: 'diagram', layout: 'tree', description: 'The tree.', nodes, edges };
    const block = { stage,
        steps: [step(['a', 'b', 'c'], { a: 'f = 3' }, 'a'),
                step(keys, { a: 'f = 3', o: '\\(f = 12\\)' }, 'o')] };
    document.querySelector('main').replaceChildren(renderWalkthrough(block, () => null));
}"""


def test_tree_walkthrough_keeps_the_lecture_shape_reveals_nodes_and_writes_values(
    course_browser: Browser, project: Path
) -> None:
    from tum_mcp.course.app.preview import Handler, PreviewServer

    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "app"))
    ) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with course_browser.new_context(viewport={"width": 1440, "height": 900}) as context:
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
                page.locator("[data-block-index]").first.wait_for()
                page.evaluate(TREE_WALKTHROUGH)
                hidden = page.locator('[data-node-key="o"]')
                expect(hidden).to_have_attribute("visibility", "hidden")
                expect(page.locator('[data-node-key="a"] .node-value')).to_have_text("f = 3")
                page.get_by_role("button", name="Next step", exact=True).click()
                expect(hidden).to_have_attribute("visibility", "visible")
                expect(page.locator('[data-node-key="o"] .node-value')).to_contain_text("f")
                boxes = page.evaluate("""() => Object.fromEntries(
                    [...document.querySelectorAll('[data-node-key]')]
                    .map(group => { const box = group.getBBox(); return [group.dataset.nodeKey,
                        [box.x, box.y, box.x + box.width, box.y + box.height]]; }))""")
        finally:
            server.shutdown()
            worker.join(timeout=3)
    centre = {key: (box[0] + box[2]) / 2 for key, box in boxes.items()}
    middle = {key: (box[1] + box[3]) / 2 for key, box in boxes.items()}
    levels = ["a", "bc", "defg", "hijklmno"]
    for level in levels:
        assert len({round(middle[key]) for key in level}) == 1
        xs = [centre[key] for key in level]
        assert xs == sorted(xs) and len(set(xs)) == len(xs)
    for index, key in enumerate("abcdefg"):
        left, right = "abcdefghijklmno"[2 * index + 1], "abcdefghijklmno"[2 * index + 2]
        assert abs(centre[key] - (centre[left] + centre[right]) / 2) < 1
    for one in boxes.values():
        for other in boxes.values():
            if one is not other:
                assert (
                    one[2] <= other[0]
                    or other[2] <= one[0]
                    or one[3] <= other[1]
                    or other[3] <= one[1]
                )


def test_walkthrough_marks_only_the_traversed_direction(
    course_browser: Browser, project: Path
) -> None:
    from tum_mcp.course.app.preview import Handler, PreviewServer

    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "app"))
    ) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with course_browser.new_context() as context:
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
                page.locator("[data-block-index]").first.wait_for()
                page.evaluate("""async () => {
                    const { renderWalkthrough } = await import('./runtime/reading/walkthrough.mjs');
                    const step = (start, end) => ({ action: `Move ${start} to ${end}`,
                        why: 'Follow this directed edge.', active: [end], visited: [start],
                        frontier: [], edges: [{start, end}], state: [] });
                    const block = { label: 'Forward', stage: {kind: 'diagram',
                        description: 'Two directed links.',
                        nodes: [{key: 's', label: 'S', row: 0, col: 0},
                                {key: 'g', label: 'G', row: 0, col: 1}],
                        edges: [{start: 's', end: 'g', directed: true},
                                {start: 'g', end: 's', directed: true}]},
                        steps: [step('s', 'g'), step('g', 's')],
                        variant: { label: 'Reverse', steps: [step('g', 's'), step('s', 'g')] } };
                    const walk = renderWalkthrough(block, () => null);
                    document.querySelector('main').replaceChildren(walk);
                }""")
                forward = page.locator('[data-edge-key="s--g"]')
                reverse = page.locator('[data-edge-key="g--s"]')
                expect(forward).to_have_class("edge active")
                expect(reverse).to_have_class("edge")
                previous = page.get_by_role("button", name="Previous step", exact=True)
                expect(previous).to_be_enabled()
                previous.click()
                expect(reverse).to_have_class("edge active")
                page.get_by_role("button", name="Next step", exact=True).click()
                expect(forward).to_have_class("edge active")
                page.get_by_role("button", name="Next step", exact=True).click()
                expect(forward).to_have_class("edge")
                expect(reverse).to_have_class("edge active")
                page.get_by_role("button", name="Reverse", exact=True).click()
                expect(forward).to_have_class("edge active")
                expect(reverse).to_have_class("edge")
                page.evaluate("""async () => {
                    const { renderBlockBody } = await import('./runtime/reading/reading.mjs');
                    const frame = (key, caption) => ({ active: [key], visited: [],
                        frontier: [], edges: [], state: [], caption });
                    const blocks = [
                        {kind: 'diagram', description: 'Two states.',
                         nodes: [{key:'a',label:'A',row:0,col:0},
                                 {key:'b',label:'B',row:0,col:1}], edges: [],
                         frames: [frame('a','First state'),frame('b','Second state')]},
                        {kind: 'code', language: 'python', code: 'x = 1\\nx = 2',
                         walkthrough: [{lines:'1',note:'Set one.'},{lines:'2',note:'Set two.'}]},
                        {kind:'derivation', walkthrough:true, symbols:[], groups:[{lines:[
                            {latex:'1+1=2',reason:'Add.'}, {latex:'2+1=3',reason:'Add one.'}
                        ]}]}
                    ];
                    document.querySelector('main').append(...blocks.map(renderBlockBody));
                }""")
                for selector in (
                    ".surface.diagram",
                    ".code-walkthrough",
                    ".derivation.walkthrough",
                ):
                    stepper = page.locator(selector)
                    count = stepper.locator(".diagram-controls .small, .code-walk-count")
                    previous = stepper.get_by_role(
                        "button", name=re.compile("Previous (step|stop)")
                    )
                    following = stepper.get_by_role("button", name=re.compile("Next (step|stop)"))
                    previous.click()
                    expect(count).to_contain_text("Step 2 of 2")
                    following.click()
                    expect(count).to_contain_text("Step 1 of 2")
                    page.keyboard.press("ArrowLeft")
                    expect(count).to_contain_text("Step 2 of 2")
                    page.keyboard.press("ArrowRight")
                    expect(count).to_contain_text("Step 1 of 2")
        finally:
            server.shutdown()
            worker.join(timeout=3)


def test_local_browser_preserves_defaults_and_disables_windows_port_randomization(
    course_browser: Browser,
) -> None:
    def flags(browser: Browser) -> tuple[str, set[str]]:
        session = browser.new_browser_cdp_session()
        try:
            arguments = TypeAdapter(tuple[str, ...]).validate_python(
                session.send("Browser.getBrowserCommandLine")["arguments"]
            )
        finally:
            session.detach()
        disabled = next(
            value.partition("=")[2].split(",")
            for value in reversed(arguments)
            if value.startswith("--disable-features=")
        )
        return arguments[0], set(disabled)

    executable, actual = flags(course_browser)
    with course_browser.new_context() as context:
        windows = context.new_page().evaluate("navigator.platform") == "Win32"
    with course_browser.browser_type.launch(
        executable_path=executable, headless=True, args=["--enable-automation"]
    ) as baseline:
        _, expected = flags(baseline)
    if windows:
        expected.add("TcpPortRandomizationWin")
    assert actual == expected


@pytest.mark.parametrize("missing", [None, "runtime/study/flashcards.mjs"])
def test_secondary_browser_smoke_loads_compiled_assets_and_rejects_missing_modules(
    course_browser: Browser, project: Path, missing: str | None
) -> None:
    from browser_consumer_fixture import study_smoke

    site = project / "app"
    if missing is not None:
        (site / missing).unlink()
        with pytest.raises((AssertionError, BrowserTimeout)):
            study_smoke(course_browser, site, "bfs")
    else:
        result = study_smoke(course_browser, site, "bfs")
        assert result["passed"]
        assert result["views"] == ["content", "flashcards", "practice"]
        assert result["widths"] == [390, 1440]


IMAGE_WALKTHROUGH = """async () => {
    const { renderWalkthrough } = await import('./runtime/reading/walkthrough.mjs');
    const { renderBlockBody } = await import('./runtime/reading/reading.mjs');
    const step = (action, more) => ({ action, why: 'Rows plus columns.', active: [], frontier: [],
        visited: [], edges: [], state: [], ...more });
    const block = { stage: { kind: 'figure', alt: 'Two boards.', image: 'figures/board.png' },
        steps: [step('Measure tile 1.',
                     { regions: [{ x: 0.1, y: 0.2, w: 0.25, h: 0.5, label: '3' }] }),
                step('The next state.', { frame: 'figures/board-2.png' })] };
    document.querySelector('main').replaceChildren(renderWalkthrough(block, renderBlockBody));
}"""


def test_an_image_walkthrough_outlines_regions_on_the_picture_and_swaps_frames(
    course_browser: Browser, project: Path
) -> None:
    from PIL import Image

    from tum_mcp.course.app.preview import Handler, PreviewServer

    figures = project / "app" / "figures"
    figures.mkdir(exist_ok=True)
    Image.new("RGB", (800, 400), "white").save(figures / "board.png")
    Image.new("RGB", (800, 400), "lightgray").save(figures / "board-2.png")
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "app"))
    ) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with course_browser.new_context(viewport={"width": 390, "height": 844}) as context:
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
                page.locator("[data-block-index]").first.wait_for()
                page.evaluate(IMAGE_WALKTHROUGH)
                image = page.locator(".figure-frame img")
                expect(image).to_have_js_property("complete", True)
                expect(page.locator(".figure-outline")).to_have_count(1)
                expect(page.locator(".figure-region-label")).to_have_text("3")
                picture, overlay, outline = (
                    page.locator(selector).bounding_box()
                    for selector in (".figure-frame img", ".figure-regions", ".figure-outline")
                )
                page.get_by_role("button", name="Next step", exact=True).click()
                expect(image).to_have_attribute("src", "figures/board-2.png")
                expect(page.locator(".figure-outline")).to_have_count(0)
        finally:
            server.shutdown()
            worker.join(timeout=3)
    assert picture and overlay and outline
    assert all(abs(picture[key] - overlay[key]) < 1 for key in ("x", "y", "width", "height"))
    assert abs(outline["x"] - (picture["x"] + 0.1 * picture["width"])) < 3
    assert abs(outline["width"] - 0.25 * picture["width"]) < 4


def test_a_visual_hidden_at_a_width_is_skipped_without_waiting(course_browser: Browser) -> None:
    import time

    from tum_mcp.course.app.visuals import _shoot

    with course_browser.new_context(viewport={"width": 390, "height": 900}) as context:
        page = context.new_page()
        page.set_content('<div id="shown">a</div><div id="hidden" style="display:none">b</div>')
        started = time.monotonic()
        assert _shoot(page, "#hidden", 390) is None
        assert time.monotonic() - started < 5
        assert _shoot(page, "#shown", 390)


def test_a_tree_without_a_reveal_order_keeps_unreached_nodes_faint(
    course_browser: Browser, project: Path
) -> None:
    from tum_mcp.course.app.preview import Handler, PreviewServer

    faint = TREE_WALKTHROUGH.replace("visible_nodes: shown, ", "")
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "app"))
    ) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with course_browser.new_context() as context:
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
                page.locator("[data-block-index]").first.wait_for()
                page.evaluate(faint)
                leaf, root = (
                    page.locator('[data-node-key="o"]'),
                    page.locator('[data-node-key="a"]'),
                )
                expect(leaf).to_have_attribute("visibility", "visible")
                expect(leaf).to_have_class(re.compile(r"\bunreached\b"))
                expect(root).not_to_have_class(re.compile(r"\bunreached\b"))
                page.get_by_role("button", name="Next step", exact=True).click()
                expect(leaf).not_to_have_class(re.compile(r"\bunreached\b"))
        finally:
            server.shutdown()
            worker.join(timeout=3)
