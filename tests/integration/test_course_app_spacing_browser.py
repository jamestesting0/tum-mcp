"""Spacing by relationship: every control sits the same distance after the content it opens."""

import json
import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser, Route, expect
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.preview import Handler, PreviewServer

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
    el.matches('.disclosure:not(.pending-sheets), .exercise-help, .exercise-actions, .pill-panel');
  const heading = el => el.matches('h1, h2, h3, h4, h5, h6, .section-heading');
  const shown = el => el.getBoundingClientRect().height > 0 && !el.matches('.visually-hidden')
    && !['absolute', 'fixed'].includes(getComputedStyle(el).position);
  // A block body's first element starts at the body's edge, so margins never stack there:
  // measure to that element (through the question context that wraps the bodies).
  const lead = el => {
    const body = el.matches('.question-context') ? el.firstElementChild : el;
    return body.firstElementChild || body;
  };
  const seen = (a, b) =>
    Math.round(lead(b).getBoundingClientRect().top - a.getBoundingClientRect().bottom);
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
      if (a.matches('.definitions') && b.matches('.block-body')) {
        found.push(['passage', gap, b.className]);
      }
      // Content relations: a prompt to its context, a heading to its first block, block to block.
      if (a.matches('legend') && b.matches('.question-context')) {
        found.push(['prompt', seen(a, b), b.className]);
      }
      if (a.matches('.section-heading') && b.matches('.block-body')) {
        found.push(['heading', seen(a, b), b.className]);
      }
      if (a.matches('.block-body') && b.matches('.block-body')
          && parent.matches('.reading-material, .question-context, .model-answer')) {
        found.push(['block', seen(a, b), b.className]);
      }
    }
  }
  return {
    found, related: px('--space-related'), between: px('--space-between'), passage: px('--s4'),
    prompt: px('--space-related'), heading: px('--space-heading'), block: px('--space-block')
  };
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
        "#study/components/practice",
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
    # The text-and-icon search button needs the same glyph styling as icon-only buttons.
    icon = page.locator(".sidebar-search svg").evaluate(
        """svg => {
          const style = getComputedStyle(svg);
          return {
            width: parseFloat(style.width), height: parseFloat(style.height),
            fill: style.fill, stroke: style.stroke
          };
        }"""
    )
    assert 0 < icon["width"] <= 24 and 0 < icon["height"] <= 24
    assert icon["fill"] == "none" and icon["stroke"] != "none"
    page.close()
    assert {"related", "prompt", "heading", "block"} <= {relation for _, relation, _, _ in measured}
    assert [m for m in measured if m[2]] == []


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_completed_outline_title_keeps_its_row_and_scroll(
    course_browser: Browser, example_url: str, width: int, theme: str, tmp_path: Path
) -> None:
    page = course_browser.new_page(viewport={"width": width, "height": 500}, color_scheme=theme)
    title = "Formulate a search and trace breadth-first search across the map"

    def long_title(route: Route) -> None:
        response = route.fetch()
        data = json.loads(response.text().removeprefix("export default ").removesuffix(";\n"))
        unit = next(unit for unit in data["units"] if unit["key"] == "components")
        unit.update(title=title, path=["Lecture 1 · A long introduction to search algorithms"])
        data["units"].extend(
            unit | {"key": f"extra-{index}", "title": f"{title} {index}"} for index in range(8)
        )
        route.fulfill(response=response, body=f"export default {json.dumps(data)};\n")

    def classic_scrollbar(route: Route) -> None:
        response = route.fetch()
        route.fulfill(
            response=response,
            body=response.text() + "\n.sidebar-body::-webkit-scrollbar { width: 15px }",
        )

    page.route("**/data.mjs", long_title)
    if theme == "dark":
        page.route("**/styles.css", classic_scrollbar)
    try:
        page.goto(example_url + "#study/components/content")
        if width == 390:
            page.locator(".outline-toggle").click()
        link = page.get_by_role("link", name=title, exact=True)
        expect(link).to_be_visible()
        before = link.bounding_box()
        assert before is not None
        link.click(button="right")
        page.get_by_role("menuitem", name="Mark as completed").click()
        link = page.get_by_role("link", name=title + " (completed)", exact=True)
        expect(link).to_be_visible()
        after = link.bounding_box()
        marker = link.locator(".done-mark svg").bounding_box()
        title_box = link.locator(".unit-title").bounding_box()
        assert after and marker and title_box
        assert after["height"] == before["height"]
        assert abs(marker["y"] - title_box["y"]) <= 6
        assert marker["x"] > title_box["x"] + title_box["width"] / 2
        capture = os.environ.get("TUM_MCP_QA_CAPTURE") == "1"
        if capture:
            page.locator(".sidebar").screenshot(path=tmp_path / "outline.png")
        scroll = page.locator(".sidebar-body").evaluate(
            """body => {
              for (const group of body.querySelectorAll('.unit-group')) group.open = true;
              const main = document.querySelector('main'), before = main.scrollTop;
              body.scrollTop = body.scrollHeight;
              const noOverflow = body.scrollWidth === body.clientWidth;
              return [body.scrollTop, noOverflow, main.scrollTop === before];
            }"""
        )
        assert scroll[0] > 0 and scroll[1:] == [True, True]
        expect(page.locator(".sidebar-footer")).to_be_in_viewport()
        if capture:
            page.locator(".sidebar").screenshot(path=tmp_path / "outline-end.png")
        page.reload()
        if width == 390 and not link.is_visible():
            page.locator(".outline-toggle").click()
        expect(link).to_be_visible()
        link.focus()
        page.keyboard.press("Shift+F10")
        page.get_by_role("menuitem", name="Mark as not completed").press("Enter")
        expect(page.get_by_role("link", name=title, exact=True)).to_be_focused()
    finally:
        page.close()

