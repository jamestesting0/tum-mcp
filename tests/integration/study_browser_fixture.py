"""Verify the installed study renderer with synthetic sources in owned Chromium."""

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Route


def study_website(browser: Browser) -> dict[str, object]:
    """Exercise packaged study assets through the same owned Chromium/WSL transport."""
    from tum_mcp.study_cli import demo

    with tempfile.TemporaryDirectory(prefix="tum-study-browser-") as temporary:
        project = Path(temporary) / "Synthetic course"
        with redirect_stdout(io.StringIO()):
            demo(project)
        site = project / "study"
        content = json.loads((site / "content.json").read_bytes())
        errors = []

        def serve(route: Route) -> None:
            url = urlsplit(route.request.url)
            name = url.path.removeprefix("/") or "index.html"
            assert url.netloc == "study.invalid" and name in {
                "index.html",
                "styles.css",
                "app.mjs",
                "dom.mjs",
                "reading.mjs",
                "learning.mjs",
                "navigation.mjs",
                "flashcards.mjs",
                "data.mjs",
            }
            mime = (
                "text/html"
                if name.endswith(".html")
                else "text/css"
                if name.endswith(".css")
                else "text/javascript"
            )
            route.fulfill(status=200, content_type=mime, body=(site / name).read_bytes())

        for width in (390, 1440):
            for theme in ("light", "dark"):
                context = browser.new_context(
                    viewport={"width": width, "height": 900}, color_scheme=theme
                )
                context.route("**/*", serve)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto("https://study.invalid/#bfs/content")
                page.get_by_role(
                    "heading",
                    name=next(u["title"] for u in content["units"] if u["key"] == "bfs"),
                    exact=True,
                ).wait_for()
                assert page.locator("math").count() > 0
                code = next(
                    block
                    for u in content["units"]
                    if u["key"] == "bfs"
                    for block in u["blocks"]
                    if block["kind"] == "code"
                )
                assert page.locator(".code-region code").inner_text() == code["code"]
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.get_by_role("button", name="Next step", exact=True).click()
                page.get_by_role("button", name="Previous step", exact=True).click()
                content_tab = page.get_by_role("tab", name="Content", exact=True)
                content_tab.focus()
                page.keyboard.press("ArrowRight")
                page.locator(".flashcard").click()
                page.locator('[data-card-action="got"]').click()
                page.reload()
                page.locator(".flashcard").click()
                assert (
                    page.locator('[data-card-action="got"]').get_attribute("aria-pressed") == "true"
                )
                page.get_by_role("tab", name="Practice", exact=False).click()
                unit = next(unit for unit in content["units"] if unit["key"] == "bfs")
                question = unit["questions"][0]
                option = next(
                    option for option in question["options"] if option["key"] == question["correct"]
                )
                page.get_by_role("radio", name=option["text"], exact=True).check()
                page.get_by_role("button", name="Check answer", exact=True).click()
                assert page.get_by_role("heading", name="Correct", exact=True).is_visible()
                assert page.get_by_text(option["feedback"], exact=True).is_visible()
                if width < 800:
                    page.get_by_role("button", name="Expand course outline", exact=True).click()
                page.get_by_role("button", name="Collapse course outline", exact=True).click()
                assert page.locator("html").get_attribute("data-outline") == "collapsed"
                page.get_by_role("button", name="Expand course outline", exact=True).click()
                assert page.locator(".unit-group[open]").count() == 2
                theme_button = page.get_by_role(
                    "button",
                    name="Use light theme" if theme == "dark" else "Use dark theme",
                    exact=True,
                )
                theme_button.click()
                assert page.locator("html").get_attribute("data-theme") != theme
                page.get_by_role("navigation", name="Study views", exact=True).get_by_role(
                    "link", name="Flashcards", exact=True
                ).click()
                page.locator(".flashcard").focus()
                page.keyboard.press("Space")
                assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
                page.keyboard.press("Space")
                page.keyboard.press("1")
                assert (
                    page.locator('[data-card-action="again"]').get_attribute("aria-pressed")
                    == "true"
                )
                page.get_by_role("button", name="Again", exact=True).focus()
                page.keyboard.press("Space")
                assert page.locator(".flashcard").get_attribute("data-revealed") == "true"
                page.keyboard.press("ArrowRight")
                assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
                assert not page.locator(".card-ratings").is_visible()
                page.keyboard.press("ArrowLeft")
                page.keyboard.press("ArrowLeft")
                assert page.locator('[data-card-action="previous"]').is_disabled()
                assert page.evaluate("document.activeElement.classList.contains('flashcard')")
                page.keyboard.down("Space")
                page.keyboard.down("Space")
                page.keyboard.up("Space")
                assert page.locator(".flashcard").get_attribute("data-revealed") == "true"
                context.close()
        # Long technical identifiers must wrap in both outline layouts.
        stressed = json.loads(
            (site / "data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
        )
        stressed["course"]["title"] = "CourseIdentifierWithoutSpaces" * 5
        for unit in stressed["units"]:
            unit["title"] = "LongTechnicalIdentifierWithoutSpaces" * 5
            unit["label"] = unit["path"][-1]

        def serve_stress(route: Route) -> None:
            if urlsplit(route.request.url).path == "/data.mjs":
                route.fulfill(
                    status=200,
                    content_type="text/javascript",
                    body="export default " + json.dumps(stressed) + ";",
                )
            else:
                serve(route)

        for width in (390, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900})
            context.route("**/*", serve_stress)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            for view in ("content", "flashcards", "practice"):
                page.goto("https://study.invalid/#bfs/" + view)
                page.locator("h1").wait_for()
                assert (
                    page.locator(".unit-header .eyebrow")
                    .inner_text()
                    .lower()
                    .count(stressed["units"][1]["label"].lower())
                    == 1
                )
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.locator(".sidebar,.main,.reading").evaluate_all(
                    "elements => elements.filter(e => e.clientWidth)"
                    ".every(e => e.scrollWidth <= e.clientWidth)"
                )
            context.close()
        assert errors == [], errors
        return {
            "views": ["content", "flashcards", "practice"],
            "widths": [390, 1440],
            "themes": ["light", "dark"],
            "source": "packaged_synthetic_demo",
            "passed": True,
        }
