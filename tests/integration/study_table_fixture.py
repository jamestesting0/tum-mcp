"""Exercise intrinsic table sizing with asymmetric prose and wide tokens."""

import json
from pathlib import Path

from playwright.sync_api import Page


def table_layout_checks(page: Page, project: Path) -> None:
    from tum_mcp.study_build import build

    source = project / "study/content.json"
    original = source.read_bytes()
    content = json.loads(original)
    unit = next(unit for unit in content["units"] if unit["key"] == "bfs")
    block = next(block for block in unit["blocks"] if block["kind"] == "table")
    block["columns"] = ["Part", "Ask", "Avoid"]
    block["rows"] = [
        [
            "Context",
            "Where does the recurring problem occur?",
            "A setting so broad that every design fits.",
        ],
        [
            "Problem",
            "Which complexity or change must be managed?",
            "Naming a pattern before identifying the pressure.",
        ],
        [
            "Solution",
            "Which responsibilities and relationships contain the change?",
            "Treating a diagram as a complete implementation.",
        ],
    ]
    try:
        source.write_text(json.dumps(content), encoding="utf-8")
        build(project)
        page.reload()
        page.locator("table tbody th").first.wait_for()
        widths = []
        for width in (320, 390, 800, 1440, 1920):
            page.set_viewport_size({"width": width, "height": 900})
            for collapsed in (False, True) if width >= 800 else (True,):
                toggle = page.get_by_role(
                    "button",
                    name="Collapse course outline" if collapsed else "Expand course outline",
                    exact=True,
                )
                if toggle.count():
                    toggle.focus()
                    toggle.click()
                result = page.locator(".table-region").evaluate("""region => {
                  const table = region.querySelector('table');
                  const labels = [...table.querySelectorAll('tbody th')].map(cell => {
                    const range = document.createRange(); range.selectNodeContents(cell);
                    return {text: cell.textContent, lines: range.getClientRects().length};
                  });
                  return {labels, width: table.clientWidth, available: region.clientWidth,
                    pageOverflow: document.documentElement.scrollWidth > innerWidth};
                }""")
                assert all(label["lines"] == 1 for label in result["labels"]), result
                assert not result["pageOverflow"], result
                if width == 1440 and collapsed:
                    widths.append(result["width"])
                if width == 390:
                    assert result["width"] <= result["available"], result
                    widths.append(result["width"])
        assert widths[-1] > widths[0], widths
        page.set_viewport_size({"width": 390, "height": 900})
        region = page.locator(".table-region")
        region.locator("td").first.evaluate(
            "cell => cell.textContent = 'UnbrokenIdentifier'.repeat(30)"
        )
        assert region.evaluate("element => element.scrollWidth > element.clientWidth")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        region.focus()
        page.keyboard.press("ArrowRight")
        page.wait_for_function("() => document.querySelector('.table-region').scrollLeft > 0")
    finally:
        source.write_bytes(original)
        build(project)
        page.set_viewport_size({"width": 390, "height": 900})
        page.reload()
        page.locator(".reading-material").first.wait_for()
