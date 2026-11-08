"""Exercise the actual static export under a Pages-style project path."""

import json
import mimetypes
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread

import pytest
from documents import content_file
from playwright.sync_api import Browser, expect, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from study_explore_fixture import add_explore
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.build import build
from tum_mcp.course.app.preview import PreviewServer
from tum_mcp.course.app.publish_site import export_site
from tum_mcp.course.project.store import load_state
from tum_mcp.moodle.browser_runtime import browser_driver, launch_loopback_browser
from tum_mcp.moodle.browsers import discover_browsers

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


class StaticHandler(SimpleHTTPRequestHandler):
    # Model GitHub Pages rather than the Windows test host's file associations.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".woff2": "font/woff2",
    }

    def log_message(self, format: str, *args: str) -> None:
        return


def test_hosted_site_under_project_path_keeps_learning_and_browser_progress(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mimetypes.init()
    monkeypatch.setitem(mimetypes.types_map, ".mjs", "text/plain")
    # Given the exported renderer under a repository subpath with no backend.
    add_explore(project)
    build(project, publish=False)
    site = tmp_path / "host/course"
    site.mkdir(parents=True)
    for name, value in export_site(project).items():
        target = site / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    content = json.loads((content_file(project, "study")).read_bytes())
    course_title = load_state(project).course.title
    choices = discover_browsers()
    assert choices, "Install a Chromium browser for the requested hosted-site QA."
    destination = os.environ.get("TUM_MCP_HOSTED_QA_PATH")
    evidence = Path(destination) if destination else None
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
    server = PreviewServer(("127.0.0.1", 0), partial(StaticHandler, directory=str(site.parent)))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    errors: list[str] = []
    requests: list[str] = []
    captures: list[str] = []
    try:
        with browser_driver(choices[0]), sync_playwright() as playwright:
            browser = launch_loopback_browser(playwright.chromium, choices[0])
            try:
                # When opening the complete hosted site on phones and desktop displays.
                for width in (390, 1440):
                    for theme in ("light", "dark"):
                        context = browser.new_context(
                            viewport={"width": width, "height": 900},
                            color_scheme=theme,
                            is_mobile=width == 390,
                            has_touch=width == 390,
                            device_scale_factor=3 if width == 390 else 1,
                        )
                        page = context.new_page()
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on(
                            "console",
                            lambda message: (
                                errors.append(message.text) if message.type == "error" else None
                            ),
                        )
                        page.on("request", lambda request: requests.append(request.url))
                        base = f"http://127.0.0.1:{server.server_port}/course/"
                        states = [("home", "", course_title, None)]
                        states.append(
                            (
                                "bfs-explore",
                                "#bfs/explore",
                                next(u["title"] for u in content["units"] if u["key"] == "bfs"),
                                "explore",
                            )
                        )
                        baseline = width == 1440 and theme == "light"
                        if baseline:
                            # Every route once; repeat responsive formats, not all route logic.
                            states.extend(
                                (
                                    f"{unit['key']}-{view}",
                                    f"#{unit['key']}/{view}",
                                    unit["title"],
                                    view,
                                )
                                for unit in content["units"]
                                for view in ("content", "flashcards", "practice")
                            )
                            states.extend(
                                (f"revision-{view}", f"#revision?view={view}", "Revision", view)
                                for view in ("flashcards", "practice")
                            )
                        else:
                            states.extend(
                                (
                                    f"{unit['key']}-content",
                                    f"#{unit['key']}/content",
                                    unit["title"],
                                    "content",
                                )
                                for unit in content["units"]
                                if unit["key"] in {"graphs", "bfs", "weighted", "probability"}
                            )
                        for name, fragment, expected, view in states:
                            page.goto(base + fragment)
                            # The bootstrap has an h1 too; require the actual route.
                            try:
                                page.get_by_role("heading", name=expected, exact=True).wait_for(
                                    timeout=10000
                                )
                                if view is not None:
                                    page.locator("#panel-" + view).wait_for(
                                        state="visible", timeout=10000
                                    )
                            except PlaywrightTimeoutError:
                                body = page.locator("body").inner_text()[:1500]
                                pytest.fail(
                                    f"Hosted route did not render: {page.url}; "
                                    f"errors={errors[:5]}; body={body}"
                                )
                            assert errors == [], errors
                            page.evaluate("document.fonts.ready")
                            assert page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            )
                            if evidence:
                                filename = f"{width}-{theme}-{name}.png"
                                page.screenshot(path=str(evidence / filename))
                                captures.append(filename)
                                if page.evaluate(
                                    "document.documentElement.scrollHeight > innerHeight"
                                ):
                                    page.evaluate(
                                        "scrollTo(0, document.documentElement.scrollHeight)"
                                    )
                                    filename = f"{width}-{theme}-{name}-end.png"
                                    page.screenshot(path=str(evidence / filename))
                                    captures.append(filename)
                        if not baseline:
                            context.close()
                            continue
                        unit = next(unit for unit in content["units"] if unit["key"] == "bfs")
                        page.goto(base + "#bfs/flashcards")
                        page.locator(".flashcard").click()
                        page.locator('[data-card-action="got"]').click()
                        page.reload()
                        page.locator(".flashcard").click()
                        assert (
                            page.locator('[data-card-action="got"]').get_attribute("aria-pressed")
                            == "true"
                        )
                        page.get_by_role("tab", name="Practice", exact=False).click()
                        question = unit["questions"][0]
                        option = next(
                            item
                            for item in question["options"]
                            if item["key"] == question["correct"]
                        )
                        page.get_by_role("radio", name=option["text"], exact=True).check()
                        page.get_by_role("button", name="Check", exact=True).click()
                        assert page.get_by_role("heading", name="Correct", exact=True).is_visible()
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        worker.join(timeout=3)
        server.server_close()
        assert not worker.is_alive(), "Hosted test server did not stop."
    # Then learning works, paths stay within the project, and no comment endpoint is contacted.
    assert errors == []
    assert requests and all("/_study/comments" not in url for url in requests)
    assert all(url.startswith(f"http://127.0.0.1:{server.server_port}/course/") for url in requests)
    if evidence:
        (evidence / "captures.json").write_text(json.dumps(captures, indent=2), encoding="utf-8")


@pytest.mark.parametrize("width,theme", [(390, "light"), (1440, "dark")])
def test_complete_public_app_keeps_learning_panels_and_lecture_timestamp_links(
    course_browser: Browser, lecture_extension: Path, tmp_path: Path, width: int, theme: str
) -> None:
    root = tmp_path / "complete"
    result = CliRunner().invoke(app, ["study", "demo", str(root), "--lectures"])
    assert result.exit_code == 0, result.output
    exported = export_site(root)
    data = json.loads(
        exported["data.mjs"].removeprefix(b"const data = ").split(b";\ndata.hosted")[0]
    )
    assert set(data["workspaces"]) == {"study", "exercises", "exam", "lectures"}
    site = tmp_path / "host/course"
    for name, content in exported.items():
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    handler = partial(StaticHandler, directory=str(site.parent))
    server = PreviewServer(("127.0.0.1", 0), handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    context = course_browser.new_context(
        viewport={"width": width, "height": 844},
        color_scheme=theme,
        is_mobile=width == 390,
        has_touch=width == 390,
        device_scale_factor=3 if width == 390 else 1,
    )
    context.route(
        "https://example.invalid/**",
        lambda route: route.fulfill(
            status=200, content_type="text/html", body="<title>Synthetic recording</title>"
        ),
    )
    page = context.new_page()
    errors, requests, failed = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.on(
        "response", lambda response: failed.append(response.url) if response.status >= 400 else None
    )
    base = f"http://127.0.0.1:{server.server_port}/course/"
    evidence = Path(os.environ.get("TUM_MCP_HOSTED_QA_PATH", str(tmp_path))) / "complete"
    evidence.mkdir(parents=True, exist_ok=True)
    lecture = data["lectures"]["lectures"][0]
    exercise = data["exercises"]["sets"][0]["exercises"][0]
    pattern = data["exam"]["patterns"][0]
    mock = data["exam"]["mocks"][0]
    sitting = data["exam"]["sittings"][0]
    variant = sitting["variants"][0]
    authored_exam = json.loads((content_file(root, "exam")).read_bytes())
    linked_concept = next(item for item in authored_exam["concepts"] if item.get("passages"))
    linked_pattern = next(
        item for item in authored_exam["patterns"] if linked_concept["key"] in item["concepts"]
    )
    states = [
        ("study", "#components/content", data["units"][0]["title"]),
        ("exercises", "#exercises/preview/controls", exercise["title"]),
        ("exam-sheet", "#exam/sheet", "Cheatsheet"),
        ("exam-pattern", f"#exam/patterns/{pattern['key']}", pattern["title"]),
        ("exam-paper", f"#exam/paper/{variant['key']}", sitting["label"]),
        ("exam-mock", f"#exam/mock/{mock['key']}", mock["title"]),
        ("lectures", f"#lectures/{lecture['key']}", lecture["title"]),
    ]
    try:
        for name, route, heading in states:
            page.goto(base + route)
            expect(page.locator("main h1")).to_contain_text(heading)
            page.evaluate("document.fonts.ready")
            expect(page.locator(".source-note:visible")).to_have_count(
                len(lecture["notes"]) if name == "lectures" else 0
            )
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
            page.screenshot(
                path=str(evidence / f"{width}-{theme}-{name}.png"), animations="disabled"
            )
            if name == "study":
                page.locator(".insight-trigger").first.click()
                expect(page.locator(".insight-tip .term-bubble")).to_be_visible()
                page.keyboard.press("Escape")
            elif name == "exercises":
                page.locator(".recall-chip").first.click()
                page.get_by_role("button", name="Open lesson", exact=True).click()
                expect(page.locator("dialog.reference-panel")).to_be_visible()
                expect(page.locator("dialog.reference-panel .source-note:visible")).to_have_count(0)
                page.screenshot(
                    path=str(evidence / f"{width}-{theme}-recall.png"), animations="disabled"
                )
                page.get_by_role("button", name="Close", exact=True).click()
                page.get_by_text("Guide", exact=True).first.click()
                page.get_by_role("button", name="Compare", exact=True).first.click()
                expect(page.locator(".feedback:visible")).not_to_have_count(0)
            elif name == "exam-pattern":
                page.locator(".recall-chip").first.click()
                page.get_by_role("button", name="Open cheatsheet", exact=True).click()
                expect(page.locator("dialog.reference-panel")).to_be_visible()
                expect(page.locator("dialog.reference-panel .source-note:visible")).to_have_count(0)
                page.screenshot(
                    path=str(evidence / f"{width}-{theme}-exam-recall.png"), animations="disabled"
                )
                page.get_by_role("button", name="Close", exact=True).click()
                page.goto(base + f"#exam/patterns/{linked_pattern['key']}")
                expect(page.locator("main h1")).to_contain_text(linked_pattern["title"])
                page.locator(".recall-chip", has_text=linked_concept["title"]).click()
                page.get_by_role("button", name="Open lesson", exact=True).click()
                passage = linked_concept["passages"][0]
                expect(
                    page.get_by_role("link", name="Open in Study", exact=True)
                ).to_have_attribute("href", f"#{passage['unit']}/content/{passage['block']}")
                page.get_by_role("button", name="Close", exact=True).click()
            elif name == "exam-sheet":
                # Related links stay behind the entry even when the fact needs no detail.
                fact = page.locator("#concept-fifo")
                expect(fact.locator("details")).to_have_count(1)
                expect(fact.locator(".exam-entry-links a").first).not_to_be_visible()
                fact.locator("summary").click()
                expect(fact.locator(".exam-entry-links a").first).to_be_visible()
                fact.locator("summary").click()
                expect(fact.locator(".exam-entry-links a").first).not_to_be_visible()
                page.locator("#concept-queue > details > summary").click()
                expect(page.locator(".exam-entry-body:visible")).not_to_have_count(0)
            elif name == "lectures":
                # Thumbnails load lazily; on a phone the notes push them below the fold.
                for image in page.locator(".lecture-thumb img").all():
                    image.scroll_into_view_if_needed()
                page.wait_for_function(
                    "() => [...document.querySelectorAll('.lecture-thumb img')]"
                    ".every(image => image.complete && image.naturalWidth > 0)"
                )
                first = page.locator(".lecture-highlight").first
                expected = lecture["highlights"][0]["url"]
                expect(first.locator(".lecture-when .lecture-time")).to_have_attribute(
                    "href", expected
                )
                expect(first.locator(".lecture-thumb")).to_have_attribute("href", expected)
                note = page.locator(".lecture-note").first
                timestamp = note.locator(".lecture-time")
                expect(timestamp).to_have_attribute("href", lecture["notes"][0]["url"])
                with page.expect_popup() as opened:
                    timestamp.click()
                popup = opened.value
                expect(popup).to_have_url(lecture["notes"][0]["url"])
                popup.close()
                page.keyboard.press("Escape")
            assert errors == [] and failed == [], (errors, failed)
        assert all(url.startswith(base) or url == lecture["notes"][0]["url"] for url in requests)
        assert not any(
            "/materials/" in url or "/videos/" in url or "/_study/" in url for url in requests
        )
    finally:
        context.close()
        server.shutdown()
        worker.join(timeout=3)
        server.server_close()
        assert not worker.is_alive()
