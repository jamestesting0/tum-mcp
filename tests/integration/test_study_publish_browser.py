"""Exercise the actual static export under a Pages-style project path."""

import json
import mimetypes
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import discover_browsers
from tum_mcp.study_publish_site import export_site
from tum_mcp.study_store import load_state

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
    site = tmp_path / "host/course"
    site.mkdir(parents=True)
    for name, value in export_site(project).items():
        (site / name).write_bytes(value)
    content = json.loads((project / "study/content.json").read_bytes())
    course_title = load_state(project).course.title
    choices = discover_browsers()
    assert choices, "Install a Chromium browser for the requested hosted-site QA."
    destination = os.environ.get("TUM_MCP_HOSTED_QA_PATH")
    evidence = Path(destination) if destination else None
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(StaticHandler, directory=str(site.parent))
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    errors: list[str] = []
    requests: list[str] = []
    captures: list[str] = []
    try:
        with browser_driver(choices[0]), sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=choices[0].executable, headless=True, args=["--enable-automation"]
            )
            try:
                # When opening the complete hosted site on phones and desktop displays.
                for width in (390, 1440, 1920):
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
                        states.extend(
                            (f"{unit['key']}-{view}", f"#{unit['key']}/{view}", unit["title"], view)
                            for unit in content["units"]
                            for view in ("content", "flashcards", "practice")
                        )
                        states.extend(
                            (f"revision-{view}", f"#revision?view={view}", "Revision", view)
                            for view in ("flashcards", "practice")
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
                        page.get_by_role("button", name="Check answer", exact=True).click()
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
        (evidence / "captures.json").write_text(json.dumps(captures, indent=2))
