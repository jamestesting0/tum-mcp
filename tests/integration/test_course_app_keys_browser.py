"""Pagers follow the arrow keys while focus is inside them, but never steal them from a field."""

import json
import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser, expect
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.study_preview import Handler, PreviewServer

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Explicit owned browser QA."
)


@pytest.fixture
def example_url(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "example"
    result = CliRunner().invoke(app, ["study", "demo", str(root)])
    assert result.exit_code == 0, result.output
    # A second practice question, so there is a next one to page to.
    path = root / "app/content.json"
    content = json.loads(path.read_text())
    question = content["units"][0]["questions"][0]
    content["units"][0]["questions"].append({**question, "key": question["key"] + "-again"})
    path.write_text(json.dumps(content))
    result = CliRunner().invoke(app, ["study", "build", str(root), "--local-only"])
    assert result.exit_code == 0, result.output
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(root / "app"))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_practice_and_guides_page_with_arrow_keys(
    course_browser: Browser, example_url: str
) -> None:
    page = course_browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(example_url + "#study/components/practice")
    count = page.locator("main p.small", has_text="Question").first
    expect(count).to_contain_text("Question 1 of")
    # No click first: the arrows page as soon as practice is shown.
    page.keyboard.press("ArrowRight")
    expect(count).to_contain_text("Question 2 of")
    # On a radio button Down still chooses the next option; Left pages.
    radios = page.locator(".practice-question input[type=radio]")
    radios.first.check()
    page.keyboard.press("ArrowDown")
    expect(radios.nth(1)).to_be_checked()
    expect(count).to_contain_text("Question 2 of")
    page.keyboard.press("ArrowLeft")
    expect(count).to_contain_text("Question 1 of")
    page.goto(example_url + "#exercises/preview/controls")
    page.locator("summary", has_text="Guide").first.click()
    step = page.locator(".step-count").first
    expect(step).to_have_text("Step 1 of 5")
    # Right after opening the Guide, its steps follow the arrows.
    page.keyboard.press("ArrowRight")
    expect(step).to_have_text("Step 2 of 5")
    # Paging by key leaves focus where it was, so no step button shows as pressed.
    assert page.evaluate("() => !document.activeElement.closest('.step-navigation')")
    # With focus back on the page, the guide last used still follows them.
    page.locator("main h1").click()
    page.keyboard.press("ArrowRight")
    expect(step).to_have_text("Step 3 of 5")
    page.close()
