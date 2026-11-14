import json
import os
import re
import struct
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


@pytest.mark.parametrize("width", [1280, 1440])
@pytest.mark.parametrize("contents", ["open", "closed"])
@pytest.mark.parametrize("valued", [False, True])
def test_wide_tree_fits_available_reading_space(
    course_browser: Browser, project: Path, width: int, contents: str, valued: bool
) -> None:
    from tum_mcp.course.app.preview import Handler, PreviewServer

    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "app"))
    ) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with course_browser.new_context(viewport={"width": width, "height": 900}) as context:
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
                page.locator("[data-block-index]").first.wait_for()
                page.evaluate(
                    """async ({contents, valued}) => {
                      const { renderWalkthrough } =
                        await import('./runtime/reading/walkthrough.mjs');
                      const reading = document.querySelector('.reading');
                      reading.parentElement.classList.add('has-contents');
                      document.documentElement.dataset.contents = contents;
                      const nodes = Array.from({length: 15}, (_, i) =>
                        ({key: String(i), label: `City ${i}`, shape: 'box'}));
                      const edges = nodes.slice(1).map((item, i) =>
                        ({start: String(Math.floor(i / 2)), end: item.key}));
                      const step = {action: 'Expand', why: 'Continue.', active: ['0'],
                        visited: [], frontier: ['1'], edges: [], state: []};
                      if (valued) step.node_values = Object.fromEntries(
                        nodes.map(item => [item.key, '2 + 3 = 5']));
                      const block = {stage: {kind:'diagram', layout:'tree',
                        description:'Tree', nodes, edges}, steps:[step]};
                      const small = renderWalkthrough({stage: {...block.stage,
                        nodes: nodes.slice(0, 3), edges: edges.slice(0, 2)},
                        steps: [{...step, active: [], frontier: []}]}, () => null);
                      small.id = 'small-test-tree';
                      const wide = renderWalkthrough(block, () => null);
                      wide.id = 'wide-test-tree';
                      reading.append(small, wide);
                      await new Promise(resolve =>
                        requestAnimationFrame(() => requestAnimationFrame(resolve)));
                    }""",
                    {"contents": contents, "valued": valued},
                )
                graph = page.locator("#wide-test-tree .graph-region")
                metrics = graph.evaluate("""region => {
                  const r = region.getBoundingClientRect();
                  const main = document.querySelector('main').getBoundingClientRect();
                  const outline = document.querySelector('.page-outline');
                  const o = outline && outline.getClientRects().length
                    ? outline.getBoundingClientRect() : null;
                  const nodes = [...region.querySelectorAll('[data-node-key]')]
                    .map(n => n.getBoundingClientRect());
                  return {scroll: region.scrollWidth - region.clientWidth,
                    inside: nodes.every(n => n.left >= r.left - 1 && n.right <= r.right + 1 &&
                      n.left >= main.left && n.right <= main.right &&
                      (!o || n.right <= o.left + 1)),
                    natural: Number(region.querySelector('svg').dataset.naturalWidth)};
                }""")
                assert metrics["natural"] > 850
                assert metrics["scroll"] <= 1 and metrics["inside"], metrics
                expect(page.locator("#wide-test-tree .walk-legend-item")).to_have_count(3)
                expect(page.locator("#small-test-tree .walk-legend")).to_have_count(0)
                assert page.locator("#small-test-tree .graph-region").evaluate(
                    "region => !region.style.width && !region.style.marginLeft"
                )
                if width == 1440 and contents == "open" and valued:
                    from tum_mcp.course.app.visuals import _shoot

                    shot = _shoot(page, "#wide-test-tree", width)
                    assert shot is not None
                    assert struct.unpack(">I", shot[16:20])[0] >= metrics["natural"] * 12 / 14
                    page.evaluate("""async () => {
                      document.documentElement.dataset.reference = 'open';
                      await new Promise(resolve =>
                        requestAnimationFrame(() => requestAnimationFrame(resolve)));
                    }""")
                    assert graph.evaluate("""region => {
                      const main = document.querySelector('main').getBoundingClientRect();
                      return region.getBoundingClientRect().right <= main.right - 440 + 1;
                    }""")
        finally:
            server.shutdown()
            worker.join(timeout=3)


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
                legend = page.locator(".walk-legend")
                expect(legend.locator(".walk-legend-item")).to_have_count(2)
                expect(legend.locator(".active")).to_have_count(1)
                expect(legend.locator(".visited")).to_have_count(1)
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
    faint = faint.replace(
        "document.querySelector('main').replaceChildren",
        "block.label = 'First run'; block.variant = {label: 'Second run', "
        "steps: structuredClone(block.steps)}; block.contrast = 'Independent restart.'; "
        "document.querySelector('main').replaceChildren",
    )
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
                expect(
                    page.locator(".walk-legend").get_by_text("Not reached yet", exact=True)
                ).to_be_visible()
                expect(root).not_to_have_class(re.compile(r"\bunreached\b"))
                page.get_by_role("button", name="Next step", exact=True).click()
                expect(leaf).not_to_have_class(re.compile(r"\bunreached\b"))
                page.get_by_role("button", name="Previous step", exact=True).click()
                page.get_by_role("button", name="Second run", exact=True).click()
                expect(leaf).to_have_class(re.compile(r"\bunreached\b"))
        finally:
            server.shutdown()
            worker.join(timeout=3)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_cutoff_and_discarded_nodes_are_reached_and_legend_respects_state_precedence(
    course_browser: Browser, project: Path, theme: str
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
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                page.evaluate("""async () => {
                  const { renderWalkthrough } = await import('./runtime/reading/walkthrough.mjs');
                  const nodes = 'abcdef'.split('').map(key => ({key, label: key.toUpperCase()}));
                  const edges = 'bcdef'.split('').map(end => ({start:'a', end, directed:true}));
                  const step = (active, frontier, cutoff, visited, discarded) =>
                    ({action:'Discard E after its repeated-state test.',
                      why:'E repeats a reached state. C stops at the depth limit.',
                      active, frontier, cutoff, visited, discarded, edges:[], state:[]});
                  const block = {stage:{kind:'diagram', layout:'tree',
                    description:'Tree', nodes, edges},
                    steps:[step(['a','c','e'], ['b','c','e'], ['c'],
                                ['b','c','d','e'], ['e']),
                           step(['a'], [], [], ['d'], [])]};
                  document.querySelector('main').replaceChildren(
                    renderWalkthrough(block, () => null));
                }""")
                legend = page.locator(".walk-legend")
                expect(legend.get_by_text("Cut off", exact=True)).to_be_visible()
                expect(legend.get_by_text("Discarded", exact=True)).to_be_visible()
                states = [
                    ("a", "active"),
                    ("b", "frontier"),
                    ("c", "cutoff"),
                    ("d", "visited"),
                    ("e", "discarded"),
                ]
                for key, state in states:
                    element = page.locator(f'[data-node-key="{key}"]')
                    expect(element).to_have_class(re.compile(rf"\b{state}\b"))
                    for other in {"active", "frontier", "cutoff", "visited", "discarded"} - {state}:
                        expect(element).not_to_have_class(re.compile(rf"\b{other}\b"))
                expect(page.locator('[data-node-key="f"]')).to_have_class(
                    re.compile(r"\bunreached\b")
                )
                expect(page.locator('[data-node-key="c"]')).not_to_have_class(
                    re.compile(r"\bunreached\b")
                )
                expect(page.locator('[data-node-key="e"]')).not_to_have_class(
                    re.compile(r"\bunreached\b")
                )
                page.screenshot(path=str(project.parent / f"discarded-graph-{theme}.png"))
                page.get_by_role("button", name="Next step", exact=True).click()
                expect(page.locator('[data-node-key="e"]')).not_to_have_class(
                    re.compile(r"\b(discarded|unreached)\b")
                )
                expect(page.locator('[data-node-key="c"]')).not_to_have_class(
                    re.compile(r"\bunreached\b")
                )
                page.evaluate(TREE_WALKTHROUGH)
                expect(
                    page.locator(".walk-legend").get_by_text("Cut off", exact=True)
                ).to_have_count(0)
                expect(
                    page.locator(".walk-legend").get_by_text("Discarded", exact=True)
                ).to_have_count(0)
                # Explicitly shown nodes without a semantic mark still have a visible style.
                page.evaluate("""async () => {
                  const { renderWalkthrough } = await import('./runtime/reading/walkthrough.mjs');
                  const first = {action:'Inspect the input.', why:'No node has been selected.',
                    active:[], frontier:[], visited:[], edges:[], state:[],
                    visible_nodes:['a','b']};
                  const last = {...first, action:'Select A.', active:['a']};
                  document.querySelector('main').replaceChildren(renderWalkthrough({
                    stage:{kind:'diagram', description:'A pair.', nodes:[
                      {key:'a',label:'A'}, {key:'b',label:'B'}], edges:[]},
                    steps:[first,last]}, () => null));
                }""")
                expect(
                    page.locator(".walk-legend").get_by_text("No current role", exact=True)
                ).to_be_visible()
        finally:
            server.shutdown()
            worker.join(timeout=3)


def test_search_ignores_discarded_node_keys(course_browser: Browser, project: Path) -> None:
    server, worker = _serve(project)
    try:
        with course_browser.new_context() as context:
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
            page.locator("[data-block-index]").first.wait_for()
            matches = page.evaluate("""async () => {
                const { default: data } = await import('./data.mjs');
                const block = data.units[0].blocks[0];
                block.discarded = ['discardednodeidentifier'];
                block.paragraphs = ['Searchable explanationword.'];
                const { search } = await import('./runtime/shell/search.mjs');
                return [search('discardednodeidentifier').length,
                        search('explanationword').length];
            }""")
            assert matches == [0, 1]
    finally:
        server.shutdown()
        worker.join(timeout=3)


LONG_WALK = """async ({ count, long }) => {
    const { renderWalkthrough } = await import('./runtime/reading/walkthrough.mjs');
    const why = long ? 'This reason is long on purpose. '.repeat(40) : 'Deepest first.';
    const nodes = [{ key: 'a', label: 'A', row: 0, col: 0 },
        { key: 'b', label: 'B', row: 0, col: 1 }];
    const steps = Array.from({ length: count }, (_, i) => ({
        subgoal: `Limit ${Math.floor(i * 3 / count)}`, action: `Step number ${i + 1}.`, why,
        active: [i % 2 ? 'b' : 'a'], frontier: [], visited: [], edges: [], state: [] }));
    const walk = renderWalkthrough({ stage: { kind: 'diagram', description: 'Two nodes.',
        nodes, edges: [{ start: 'a', end: 'b' }] }, steps }, () => null);
    const filler = document.createElement('div'); filler.style.height = '2000px';
    const top = document.createElement('div'); top.style.height = '600px';
    document.querySelector('main').replaceChildren(top, walk, filler);
}"""


def _serve(project: Path):
    from tum_mcp.course.app.preview import Handler, PreviewServer

    server = PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(project / "app")))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, worker


def test_a_long_walkthrough_keeps_one_row_of_adjacent_controls_and_jumps(
    course_browser: Browser, project: Path
) -> None:
    server, worker = _serve(project)
    try:
        for width in (1440, 390):
            with course_browser.new_context(viewport={"width": width, "height": 800}) as context:
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
                page.locator("[data-block-index]").first.wait_for()
                page.evaluate(LONG_WALK, {"count": 60, "long": False})
                controls = page.locator(".walk-controls")
                expect(controls.locator(".walk-dot")).to_have_count(0)
                boxes = page.evaluate(
                    """() => ['Previous step', 'Next step', 'All steps', 'jump'].map(name => {
                        const button = [...document.querySelectorAll('.walk-controls button')]
                            .find(item => name === 'jump' ? item.matches('.walk-jump')
                                : (item.getAttribute('aria-label') || item.textContent) === name);
                        const box = button.getBoundingClientRect();
                        return { top: box.top, bottom: box.bottom,
                            left: box.left, right: box.right };
                    })"""
                )
                previous, following, whole, position = boxes
                assert max(box["top"] for box in boxes) < min(box["bottom"] for box in boxes)
                assert 0 <= position["left"] - previous["right"] <= 8
                assert 0 <= following["left"] - position["right"] <= 8
                assert whole["right"] <= width
                jump = controls.locator(".walk-jump")
                expect(jump.locator(".walk-jump-count")).to_have_text("Step 1 of 60")
                expect(jump.locator(".walk-jump-group")).to_have_text("Limit 0")
                jump.click()
                page.locator(".walk-menu-group").nth(2).click()
                expect(jump.locator(".walk-jump-count")).to_have_text("Step 41 of 60")
                expect(jump).to_be_focused()
                jump.click()
                expect(page.locator('.walk-menu-step[aria-current="step"]')).to_be_focused()
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                expect(jump.locator(".walk-jump-count")).to_have_text("Step 42 of 60")
                jump.click()
                page.keyboard.press("Escape")
                expect(page.locator(".walk-menu")).to_be_hidden()
                page.keyboard.press("ArrowRight")
                expect(jump.locator(".walk-jump-count")).to_have_text("Step 43 of 60")
                page.keyboard.press("ArrowLeft")
                expect(jump.locator(".walk-jump-count")).to_have_text("Step 42 of 60")
    finally:
        server.shutdown()
        worker.join(timeout=3)


def test_stepping_a_long_explanation_keeps_the_page_still(
    course_browser: Browser, project: Path
) -> None:
    server, worker = _serve(project)
    try:
        with course_browser.new_context(viewport={"width": 1280, "height": 700}) as context:
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
            page.locator("[data-block-index]").first.wait_for()
            page.evaluate(LONG_WALK, {"count": 26, "long": True})
            centre = "item => item.scrollIntoView({block: 'center'})"
            page.locator(".walk-controls").evaluate(centre)
            place = """() => [
                Math.round(document.scrollingElement.scrollTop
                    + document.querySelector('main').scrollTop),
                Math.round(document.querySelector('.walk-controls').getBoundingClientRect().top)]"""
            before = page.evaluate(place)
            assert 0 < before[1] < 700, "the controls sit in view under the picture"
            following = page.get_by_role("button", name="Next step", exact=True)
            for number in range(2, 6):
                following.click()
                expect(page.locator(".walk-jump-count")).to_have_text(f"Step {number} of 26")
                assert page.evaluate(place) == before
    finally:
        server.shutdown()
        worker.join(timeout=3)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_grid_stage_marks_cells_draws_moves_and_keeps_written_values(
    course_browser: Browser, project: Path, theme: str
) -> None:
    server, worker = _serve(project)
    try:
        with course_browser.new_context(viewport={"width": 1440, "height": 900}) as context:
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
            page.locator("[data-block-index]").first.wait_for()
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            page.evaluate("""async () => {
                const { renderWalkthrough } = await import('./runtime/reading/walkthrough.mjs');
                const at = (grid, cell, mark) => ({ grid, cell, mark });
                const stage = { kind: 'grid', description: 'Start and goal.', grids: [
                    { key: 'start', label: 'Start', cells: [['1', ''], ['', '2']],
                      row_labels: ['0', '1'], col_labels: ['0', '1'] },
                    { key: 'goal', label: 'Goal', cells: [['', '1'], ['2', '']],
                      shaded: ['2:2'] }] };
                const steps = [
                    { action: 'Tile 1.', why: 'One column right.', state: [],
                      grid_marks: [at('start', '1:1', 'active'), at('goal', '1:2', 'active')],
                      grid_arrows: [{ start: { grid: 'start', cell: '1:1' },
                        end: { grid: 'goal', cell: '1:2' }, label: '0 + 1' }] },
                    { action: 'Tile 2.', why: 'One row down, one left.', state: [],
                      grid_marks: [at('start', '1:1', 'visited'), at('start', '2:2', 'active'),
                        at('goal', '1:1', 'discarded'), at('goal', '1:1', 'frontier')],
                      grid_values: [{ grid: 'start', cell: '1:2', value: '1' }],
                      grid_arrows: [{ start: { grid: 'start', cell: '2:2' },
                        end: { grid: 'start', cell: '1:1' } }] },
                    { action: 'Done.', why: 'Written values stay.', state: [], grid_marks: [] }];
                const walk = renderWalkthrough({ stage, steps }, () => null);
                document.querySelector('main').replaceChildren(walk);
            }""")
            cell = lambda key: page.locator(f'[data-cell="{key}"]')  # noqa: E731
            expect(cell("start:1:1")).to_have_class("grid-cell active")
            expect(cell("goal:1:2")).to_have_class("grid-cell active")
            expect(page.locator(".grid-arrow")).to_have_count(1)
            expect(page.locator(".grid-arrow-label")).to_have_text("0 + 1")
            expect(page.locator(".walk-legend .walk-legend-item")).to_have_text(
                ["Current", "Discarded", "Done", "Shaded", "No current role"]
            )
            page.get_by_role("button", name="Next step", exact=True).click()
            expect(cell("start:1:1")).to_have_class("grid-cell visited")
            expect(cell("start:2:2")).to_have_class("grid-cell active")
            expect(cell("goal:1:2")).to_have_class("grid-cell")
            expect(cell("goal:1:1")).to_have_class("grid-cell discarded")
            page.screenshot(path=str(project.parent / f"discarded-grid-{theme}.png"))
            elbow = re.compile(r"^M\S+ \S+L\S+ \S+L")
            expect(page.locator(".grid-arrow")).to_have_attribute("d", elbow)
            expect(page.locator(".grid-arrow-label")).to_have_count(0)
            value = page.locator(".grid-value").nth(1)
            expect(value).to_have_text("1")
            page.get_by_role("button", name="Next step", exact=True).click()
            expect(page.locator(".grid-arrow")).to_have_count(0)
            expect(cell("goal:1:1")).to_have_class("grid-cell")
            expect(value).to_have_text("1")
            page.get_by_role("button", name="Previous step", exact=True).click()
            page.get_by_role("button", name="Previous step", exact=True).click()
            expect(value).to_have_text("")
    finally:
        server.shutdown()
        worker.join(timeout=3)


GRID_CLEARANCE = """() => {
    const hits = [];
    for (const figure of document.querySelectorAll('.grid-figure')) {
        const values = [...figure.querySelectorAll('.grid-value')]
            .filter(item => item.textContent.trim()).map(item => item.getBBox());
        const cells = [...figure.querySelectorAll('.grid-cell rect')].map(item => item.getBBox());
        const meets = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width
            && a.y < b.y + b.height && b.y < a.y + a.height;
        for (const path of figure.querySelectorAll('.grid-arrow')) {
            const points = [...path.getAttribute('d').matchAll(/[ML]([-\\d.]+) ([-\\d.]+)/g)]
                .map(match => [Number(match[1]), Number(match[2])]);
            const boxes = points.slice(1).map(([x, y], index) => {
                const [px, py] = points[index];
                return { x: Math.min(x, px) - 3, y: Math.min(y, py) - 3,
                    width: Math.abs(x - px) + 6, height: Math.abs(y - py) + 6 };
            });
            const [hx, hy] = points.at(-1);
            boxes.push({ x: hx - 9, y: hy - 9, width: 18, height: 18 });
            for (const box of boxes) {
                if (values.some(value => meets(box, value))) hits.push('arrow');
            }
        }
        for (const label of figure.querySelectorAll('.grid-arrow-label')) {
            const box = label.getBBox();
            if ([...values, ...cells].some(item => meets(box, item))) hits.push(label.textContent);
        }
    }
    return hits;
}"""


@pytest.mark.parametrize("width", [1440, 390])
def test_grid_arrows_and_labels_never_cover_a_cell_value(
    course_browser: Browser, project: Path, width: int
) -> None:
    scenarios = json.loads(
        (Path(__file__).parents[1] / "fixtures/grid_scenarios.json").read_bytes()
    )
    server, worker = _serve(project)
    try:
        with course_browser.new_context(viewport={"width": width, "height": 900}) as context:
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/#bfs/content")
            page.locator("[data-block-index]").first.wait_for()
            page.evaluate(
                """async block => {
                    const { renderBlockBody } = await import('./runtime/reading/reading.mjs');
                    document.querySelector('main').replaceChildren(renderBlockBody(block));
                }""",
                scenarios["static"],
            )
            expect(page.locator(".grid-arrow")).to_have_count(1)
            assert page.evaluate(GRID_CLEARANCE) == []
            for block in scenarios["walkthroughs"]:
                page.evaluate(
                    """async block => {
                        const { renderWalkthrough } =
                            await import('./runtime/reading/walkthrough.mjs');
                        const walk = renderWalkthrough(block, () => null);
                        document.querySelector('main').replaceChildren(walk);
                    }""",
                    block,
                )
                following = page.get_by_role("button", name="Next step", exact=True)
                for number in range(len(block["steps"])):
                    assert page.evaluate(GRID_CLEARANCE) == [], (block["key"], number + 1)
                    following.click()
    finally:
        server.shutdown()
        worker.join(timeout=3)
