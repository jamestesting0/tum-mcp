import os
import re
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.preview import Handler, PreviewServer

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)

# Every page type of the four workspaces in the bundled demo, and whether it leads on to a
# following item. Homes never do.
PAGES = {
    "#home": False,
    "#components/content": True,
    "#components/flashcards": True,
    "#components/practice": True,
    "#revision?view=flashcards": True,
    "#exercises": False,
    "#exercises/preview/controls": False,
    "#lectures": False,
    "#exam": False,
    "#exam/sheet": True,
    "#exam/patterns/name-structure": True,
    "#exam/paper/demo-final-a": True,
    "#exam/mock/demo-forecast": False,
}
# Names the shared answer ladder replaced; finding one means a workspace drifted from it.
RETIRED = re.compile(r"Guidance|Guided steps.*|Full solution|Continue|Cheatsheet entries|\d+ / \d+")
FACTS = """() => {
    const main = document.querySelector('main');
    // Open every disclosure so the controls inside are checked too.
    main.querySelectorAll('details').forEach(details => { details.open = true; });
    const heading = main.querySelectorAll('h1');
    const label = heading[0]?.previousElementSibling;
    const names = [...main.querySelectorAll('button, summary, a, .small')].map(
        element => (element.getAttribute('aria-label') || element.textContent).trim());
    return {
        headings: heading.length,
        label: Boolean(heading[0]?.parentElement.matches('.unit-header')
            && label?.matches('.eyebrow, .page-eyebrow')),
        next: main.querySelectorAll('.next-step').length,
        names,
        overflow: document.documentElement.scrollWidth > innerWidth + 1,
    };
}"""


@pytest.mark.parametrize("width", [390, 1280])
def test_every_workspace_page_shares_one_anatomy(
    course_browser: Browser, lecture_extension: Path, tmp_path: Path, width: int
) -> None:
    root = tmp_path / "demo"
    result = CliRunner().invoke(app, ["study", "demo", str(root), "--lectures"])
    assert result.exit_code == 0, result.output
    handler = partial(Handler, directory=str(root / "app"))
    with PreviewServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        context = course_browser.new_context(viewport={"width": width, "height": 900})
        try:
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/#home")
            lecture = page.evaluate(
                "async () => (await import('./data.mjs')).default.lectures.lectures[0].key"
            )
            for route, leads_on in {**PAGES, f"#lectures/{lecture}": False}.items():
                page.goto(f"http://127.0.0.1:{server.server_port}/{route}")
                page.locator("main h1").first.wait_for()
                facts = page.evaluate(FACTS)
                assert facts["headings"] == 1, route
                assert facts["label"], route
                assert bool(facts["next"]) == leads_on, route
                assert [name for name in facts["names"] if RETIRED.fullmatch(name)] == [], route
                assert not facts["overflow"], route
            assert errors == []
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=3)
