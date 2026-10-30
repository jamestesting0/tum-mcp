# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run through: npm run test:consumer -- /path/to/package.tgz
# The controller supplies the isolated, installed backend interpreter.
"""Owned-browser verification with synthetic data and no live campus requests."""

import json
import os
import sys
import time
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Route, expect, sync_playwright
from study_browser_fixture import study_website

from tum_mcp.moodle.auth import Cookie, Session, SessionStore
from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import discover_browsers, is_wsl
from tum_mcp.moodle.config import Paths

HTML = """<!doctype html><title>Synthetic local sign-in</title>
<button onclick="document.cookie='MoodleSession=synthetic-browser-only; path=/; secure';
document.querySelector('output').textContent='Signed in';">Sign in fixture</button>
<output></output>"""


def fixture(route: Route) -> None:
    assert route.request.url.startswith("https://fixture.invalid/")
    route.fulfill(status=200, content_type="text/html", body=HTML)


class SmokeEvidence(TypedDict):
    passed: bool
    views: list[str]
    widths: list[int]


def study_smoke(browser: Browser, site: Path, unit: str) -> SmokeEvidence:
    """Check installed assets and native UI without repeating long learning journeys."""
    from tum_mcp.study_build import TEMPLATE_FILES

    errors: list[str] = []
    missing: list[str] = []

    def serve(route: Route) -> None:
        url = urlsplit(route.request.url)
        assert url.netloc == "study.invalid"
        if url.path == "/_study/comments":
            route.fulfill(status=404, content_type="application/json", body='{"error":"Static QA"}')
            return
        assert url.path.startswith("/course/")
        name = url.path.removeprefix("/course/") or "index.html"
        if name == "videos/index.json":
            route.fulfill(content_type="application/json", body='{"videos":{}}')
            return
        assert name in {*TEMPLATE_FILES, "data.mjs"}
        asset = site / name
        if not asset.is_file():
            missing.append(name)
            route.fulfill(status=404, body="Missing compiled asset")
            return
        mime = {".html": "text/html", ".css": "text/css", ".woff2": "font/woff2"}.get(
            asset.suffix, "text/javascript"
        )
        route.fulfill(content_type=mime, body=asset.read_bytes())

    for width in (390, 1440):
        context = browser.new_context(
            viewport={"width": width, "height": 900}, color_scheme="light"
        )
        try:
            context.set_default_timeout(5000)
            context.route("**/*", serve)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"https://study.invalid/course/#{unit}/content")
            assert not missing, missing
            expect(page.locator(".unit-header h1")).to_be_visible()
            page.get_by_role("tab", name="Content", exact=True).focus()
            page.keyboard.press("ArrowRight")
            expect(page.get_by_role("tab", name="Flashcards", exact=False)).to_have_attribute(
                "aria-selected", "true"
            )
            page.locator(".flashcard").click()
            page.locator('[data-card-action="got"]').click()
            page.reload()
            page.locator(".flashcard").click()
            expect(page.locator('[data-card-action="got"]')).to_have_attribute(
                "aria-pressed", "true"
            )
            page.get_by_role("tab", name="Practice", exact=False).click()
            expect(page.get_by_role("button", name="Check answer", exact=True)).to_be_visible()
            if width < 800:
                page.get_by_role("button", name="Expand course outline", exact=True).click()
            page.get_by_role("button", name="Use dark theme", exact=True).click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not missing, missing
            assert not errors, errors
        finally:
            context.close()
    return {"passed": True, "views": ["content", "flashcards", "practice"], "widths": [390, 1440]}


def main() -> None:
    from tum_mcp.course_app_paths import app_path

    journeys = os.environ.get("TUM_MCP_STUDY_BROWSER_JOURNEYS", "all")
    assert journeys in {"all", "primary"}, "Study browser journeys must be all or primary."
    browsers = discover_browsers()
    assert browsers, "No Chromium browser was found for the requested integration check."
    results = []
    for index, choice in enumerate(browsers):
        print(f"Verifying owned browser: {choice.label}", file=sys.stderr, flush=True)
        with browser_driver(choice), sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=choice.executable, headless=True, args=["--enable-automation"]
            )
            try:
                context = browser.new_context()
                context.route("**/*", fixture)
                page = context.new_page()
                page.goto("https://fixture.invalid/")
                page.get_by_role("button", name="Sign in fixture").click()
                assert page.locator("output").inner_text() == "Signed in"
                platform = page.evaluate("navigator.platform")
                if choice.windows_host:
                    assert platform == "Win32", "WSL sign-in did not run in a Windows browser."
                cdp = context.new_cdp_session(page)
                arguments = cdp.send("Browser.getBrowserCommandLine")["arguments"]
                assert "--remote-debugging-pipe" in arguments
                assert not any(value.startswith("--remote-debugging-port") for value in arguments)
                # Cookie writes cross renderer/network processes. Observe their
                # completion instead of racing the CDP snapshot after the click.
                deadline = time.monotonic() + 5
                while True:
                    cookies = [
                        Cookie.model_validate(cookie)
                        for cookie in context.cookies("https://fixture.invalid/")
                    ]
                    if cookies or time.monotonic() >= deadline:
                        break
                    page.wait_for_timeout(50)
                assert len(cookies) == 1 and cookies[0].value == "synthetic-browser-only"
                store = SessionStore(Paths.default(), storage="file")
                store.save(
                    Session(
                        generation=store.begin_login(), cookies=cookies, verified_at=time.time()
                    )
                )
                assert b"synthetic-browser-only" not in store.file("session.enc").read_bytes()
                assert store.load().cookies[0].value == "synthetic-browser-only"
                store.logout()
                full_journey = journeys == "all" or index == 0
                started = time.monotonic()
                if full_journey:
                    study = study_website(browser)
                else:
                    project = Path(os.environ["TUM_MCP_STUDY_QA_PROJECT"])
                    site = app_path(project, "index.html").parent
                    study = study_smoke(browser, site, "components")
                results.append(
                    {
                        "browser": choice.name,
                        "windowsHost": choice.windows_host,
                        "platform": platform,
                        "pipeTransport": True,
                        "encryptedSession": True,
                        "studyWebsite": study,
                        "studyCoverage": "full" if full_journey else "smoke",
                        "studySeconds": round(time.monotonic() - started, 3),
                    }
                )
            finally:
                browser.close()
    print(json.dumps({"wsl": is_wsl(), "browsers": results, "liveCampusRequests": False}))


if __name__ == "__main__":
    main()
