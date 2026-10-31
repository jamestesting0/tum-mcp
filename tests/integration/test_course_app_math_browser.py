"""KaTeX math, derivation walkthroughs and visual backgrounds in the bundled example."""

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

# The nearest ancestor that paints a background, which a drawing should blend into.
CARD = """element => {
  const paint = node => getComputedStyle(node).backgroundColor;
  let node = element.parentElement;
  while (node && paint(node) === 'rgba(0, 0, 0, 0)') node = node.parentElement;
  return [paint(element), paint(node || document.body)];
}"""


@pytest.fixture
def example_url(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "example"
    result = CliRunner().invoke(app, ["study", "demo", str(root)])
    assert result.exit_code == 0, result.output
    # The real preview server, so its Content-Security-Policy applies to KaTeX.
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(root / "app"))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)


@pytest.mark.parametrize("width,theme", [(390, "light"), (1280, "dark")])
def test_math_derivations_and_drawings_render_like_their_page(
    course_browser: Browser, example_url: str, width: int, theme: str
) -> None:
    context = course_browser.new_context(
        viewport={"width": width, "height": 900}, color_scheme=theme
    )
    errors: list[str] = []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: errors.append(message.text) if "Content Security" in message.text else None,
    )
    try:
        page.goto(example_url + "#study/components/content")
        # Inline and block math are typeset by KaTeX under the CSP, not left as source.
        expect(page.locator(".inline-math.tex .katex").first).to_be_visible()
        assert page.locator(".tex-equation .katex").count() >= 1
        assert "\\(" not in page.locator("main").inner_text()
        # A derivation aligns each line on its relation and states its reason.
        derivation = page.locator(".derivation:not(.walkthrough)").first
        assert derivation.locator(".derivation-relation .katex").count() >= 3
        assert derivation.locator(".derivation-reason").count() >= 3
        # A walkthrough reveals one line at a time, keeps earlier ones and can show all.
        walk = page.locator(".derivation.walkthrough")
        lines = walk.locator(".derivation-line")
        expect(lines.nth(1)).to_be_hidden()
        walk.get_by_role("button", name="Next step").click()
        expect(lines.nth(1)).to_be_visible()
        expect(lines.nth(0)).to_be_visible()
        expect(walk.locator("[aria-live]")).to_contain_text("Step 2 of 4")
        walk.get_by_role("button", name="Show all steps").click()
        expect(lines.nth(3)).to_be_visible()
        # Diagrams and UML sit on the background of the card that holds them.
        for region in page.locator(".graph-region, .uml-region").all():
            own, card = region.evaluate(CARD)
            assert own == card, (own, card)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()
