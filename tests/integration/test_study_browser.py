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
