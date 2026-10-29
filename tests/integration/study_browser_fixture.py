"""Verify the installed study renderer with synthetic sources in owned Chromium."""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page, Route
from study_activity_comments_fixture import activity_comment_checks
from study_comments_fixture import comment_checks
from study_inline_fixture import inline_math_checks, mobile_outline_checks
from study_revision_fixture import (
    identity_checks,
    learning_flow_checks,
    option_order_checks,
    outline_position_checks,
    practice_navigation_checks,
    revision_checks,
)
from study_table_fixture import table_layout_checks


def structure_checks(page: Page, content: dict) -> None:
    """Terms join their passage, hard ideas read as steps and figures are named images."""
    page.goto("https://study.invalid/#weighted/content")
    section = page.locator("section.read-section").filter(
        has=page.get_by_role("heading", name="Count cost, not just edges", exact=True)
    )
    assert section.locator("dl.definitions dt").inner_text() == "Tentative distance"
    assert page.get_by_role("heading", name="Tentative distance", exact=True).count() == 0
    assert section.locator("ol.steps > li").count() == 4
    # A step that opens with a short label shows the label in bold, before its own text.
    labels = section.locator("ol.steps > li > strong.item-label")
    assert labels.all_inner_texts() == ["Check:", "Initialize:", "Settle:", "Relax:"]
    page.goto("https://study.invalid/#weighted/content/tentative-distance")
    page.wait_for_function("document.activeElement?.closest('.definition-item') !== null")
    page.goto("https://study.invalid/#probability/content")
    figure = page.locator("figure.figure svg[role=img]")
    assert figure.get_attribute("aria-label").startswith("Three coins")
    assert figure.locator("text").count() == 3


def study_website(browser: Browser) -> dict[str, object]:
    """Exercise packaged study assets through the same owned Chromium/WSL transport."""
    from tum_mcp.errors import CampusError
    from tum_mcp.study_build import TEMPLATE_FILES, build
    from tum_mcp.study_comment_models import OPERATION
    from tum_mcp.study_comments import change_comment, read_comments
    from tum_mcp.study_sync import sync

    with tempfile.TemporaryDirectory(prefix="tum-study-browser-") as temporary:
        project = Path(temporary) / "Synthetic course"
        site = project / "study"
        site.mkdir(parents=True)
        fixture = Path(
            os.environ.get(
                "TUM_MCP_STUDY_QA_FIXTURE", str(Path(__file__).parents[1] / "fixtures/course_app")
            )
        )
        sync(project, fixture / "snapshot.json", course_input="Algorithms & Graphs")
        (site / "content.json").write_bytes((fixture / "content.json").read_bytes())
        build(project, publish=False)
        content = json.loads((site / "content.json").read_bytes())
        errors = []

        def serve(route: Route) -> None:
            url = urlsplit(route.request.url)
            if url.netloc == "study.invalid" and url.path == "/_study/comments":
                try:
                    result = (
                        change_comment(
                            project, OPERATION.validate_python(route.request.post_data_json)
                        )
                        if route.request.method == "POST"
                        else read_comments(project)
                    )
                    etag = f'"{result["revision"]}"'
                    unchanged = (
                        route.request.method == "GET"
                        and route.request.headers.get("if-none-match") == etag
                    )
                    route.fulfill(
                        status=304 if unchanged else 200,
                        headers={"ETag": etag},
                        content_type="application/json",
                        body="" if unchanged else json.dumps(result),
                    )
                except CampusError as error:
                    route.fulfill(
                        status=409,
                        content_type="application/json",
                        body=json.dumps({"error": error.message}),
                    )
                return
            if url.netloc == "study.invalid" and url.path == "/videos/index.json":
                # The local preview answers this for every app; this course has no videos.
                route.fulfill(status=200, content_type="application/json", body='{"videos": {}}')
                return
            name = url.path.removeprefix("/") or "index.html"
            assert url.netloc == "study.invalid" and name in {*TEMPLATE_FILES, "data.mjs"}
            mime = {".html": "text/html", ".css": "text/css", ".woff2": "font/woff2"}.get(
                Path(name).suffix, "text/javascript"
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
                assert page.locator(".sidebar").get_by_text("About", exact=True).count() == 0
                if width == 390 and theme == "light":
                    comment_checks(page, project)
                    table_layout_checks(page, project)
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
                practice_navigation_checks(page, len(unit["questions"]))
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
                if width < 800:
                    page.get_by_role("button", name="Collapse course outline", exact=True).click()
                # The single forward link replaces repeated view tabs at the end of a view.
                page.get_by_role("tab", name="Content", exact=True).click()
                page.get_by_role("navigation", name="Up next", exact=True).get_by_role(
                    "link"
                ).click()
                flashcards_tab = page.get_by_role("tab", name="Flashcards", exact=False)
                assert flashcards_tab.get_attribute("aria-selected") == "true"
                page.locator(".flashcard").focus()
                page.keyboard.press("Space")
                assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
                page.keyboard.press("Space")
                # A rating saves and advances to the next unrevealed card.
                page.keyboard.press("1")
                position = page.locator("[data-flashcards] .recall-meta")
                assert position.inner_text().startswith("2 /")
                assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
                assert page.evaluate("document.activeElement.classList.contains('flashcard')")
                page.keyboard.press("ArrowLeft")
                page.keyboard.press("Space")
                assert (
                    page.locator('[data-card-action="again"]').get_attribute("aria-pressed")
                    == "true"
                )
                # Space on a focused rating activates that rating instead of flipping.
                page.get_by_role("button", name="Again", exact=True).focus()
                page.keyboard.press("Space")
                assert position.inner_text().startswith("2 /")
                assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
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
                # Hierarchy/state transitions depend on layout, not color scheme.
                # Keep both widths; the surrounding rendering checks cover both themes.
                if theme == "light":
                    revision_checks(page, content)
                context.close()
        context = browser.new_context(viewport={"width": 390, "height": 900}, has_touch=True)
        context.route("**/*", serve)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        learning_flow_checks(page, content)
        mobile_outline_checks(page, content)
        inline_math_checks(page, project, content)
        context.close()
        for height, check in (
            (900, option_order_checks),
            (360, outline_position_checks),
            (900, structure_checks),
        ):
            context = browser.new_context(viewport={"width": 1440, "height": height})
            context.route("**/*", serve)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            check(page, content)
            context.close()
        for view in ("flashcards", "practice"):
            for pooled in (False, True):
                context = browser.new_context(viewport={"width": 390, "height": 900})
                context.route("**/*", serve)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                activity_comment_checks(page, project, content, view, pooled)
                context.close()
        # Long technical identifiers must wrap in both outline layouts.
        stressed = json.loads(
            (site / "data.mjs")
            .read_text(encoding="utf-8")
            .removeprefix("export default ")
            .removesuffix(";\n")
        )
        for unit in stressed["units"]:
            unit["flashcards"][0]["key"] = "same-item-key"
            unit["questions"][0]["key"] = "same-item-key"

        def serve_identity(route: Route) -> None:
            if urlsplit(route.request.url).path == "/data.mjs":
                route.fulfill(
                    content_type="text/javascript",
                    body="export default " + json.dumps(stressed) + ";",
                )
            else:
                serve(route)

        context = browser.new_context()
        context.route("**/*", serve_identity)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        identity_checks(page, stressed["units"])
        context.close()
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
            "source": "private_synthetic_regression_fixture",
            "passed": True,
        }
