"""Spacing by relationship: every control sits the same distance after the content it opens."""

import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.study_preview import Handler, PreviewServer

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Explicit owned browser QA."
)

# Pairs of siblings in one column: content followed by its control (Guide, Solution, Hint, an
# exercise's actions), and Practise items after each other. A section-level disclosure such as
# the sheets without exercises is a section of its own, not a control of the list above it.
GAPS = """() => {
  const root = getComputedStyle(document.documentElement);
  const px = name => parseFloat(root.getPropertyValue(name)) || 0;
  const control = el =>
    el.matches('.disclosure:not(.pending-sheets), .exercise-help, .exercise-actions');
  const heading = el => el.matches('h1, h2, h3, h4, h5, h6, .section-heading');
  const shown = el => el.getBoundingClientRect().height > 0 && !el.matches('.visually-hidden')
    && !['absolute', 'fixed'].includes(getComputedStyle(el).position);
  const found = [];
  for (const parent of document.querySelectorAll('main *')) {
    const kids = [...parent.children].filter(shown);
    for (let i = 1; i < kids.length; i++) {
      const [a, b] = [kids[i - 1], kids[i]];
      const gap = Math.round(b.getBoundingClientRect().top - a.getBoundingClientRect().bottom);
      if (control(b) && !control(a) && !heading(a)) found.push(['related', gap, b.className]);
      if (a.matches('.exam-drill-item') && b.matches('.exam-drill-item')) {
        found.push(['between', gap, b.className]);
      }
    }
  }
  return { found, related: px('--space-related'), between: px('--space-between') };
}"""


@pytest.fixture
def example_url(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "example"
    result = CliRunner().invoke(app, ["study", "demo", str(root)])
    assert result.exit_code == 0, result.output
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(root / "app"))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)


@pytest.mark.parametrize("width", [390, 1280])
def test_controls_and_practise_items_keep_one_spacing_per_relationship(
    course_browser: Browser, example_url: str, width: int
) -> None:
    page = course_browser.new_page(viewport={"width": width, "height": 900})
    measured: list[tuple[str, str, int, str]] = []
    for route in (
        "#study/components/content",
        "#exercises/preview/controls",
        "#exam/patterns/order-search",
        "#exam/patterns/name-structure",
    ):
        page.goto(example_url + route)
        page.wait_for_selector("main h1")
        page.evaluate("() => document.querySelectorAll('main details').forEach(d => d.open = true)")
        result = page.evaluate(GAPS)
        for relation, gap, name in result["found"]:
            measured.append((route, relation, gap - result[relation], name))
    page.close()
    assert any(relation == "related" for _, relation, _, _ in measured)
    assert [m for m in measured if m[2]] == []
