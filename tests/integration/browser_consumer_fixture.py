# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run through: npm run test:consumer -- /path/to/package.tgz
# The controller supplies the isolated, installed backend interpreter.
"""Owned-browser verification with synthetic data and no live campus requests."""

import io
import json
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Route, sync_playwright

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


def study_website(browser) -> dict[str, object]:
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
                page.get_by_role("button", name="Show answer", exact=True).click()
                page.get_by_role("button", name="Got it", exact=True).click()
                page.reload()
                page.get_by_role("button", name="Show answer", exact=True).click()
                assert (
                    page.get_by_role("button", name="Got it", exact=True).get_attribute(
                        "aria-pressed"
                    )
                    == "true"
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
                page.get_by_role("button", name="Focus mode", exact=True).click()
                page.keyboard.press("Escape")
                assert page.locator("html").get_attribute("data-focus") == "false"
                context.close()
        # Long technical identifiers must wrap in both outline layouts.
        stressed = json.loads(
            (site / "data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
        )
        stressed["course"]["title"] = "CourseIdentifierWithoutSpaces" * 5
        for unit in stressed["units"]:
            unit["title"] = "LongTechnicalIdentifierWithoutSpaces" * 5

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
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.locator(".sidebar,.main,.reading,.mobile-course").evaluate_all(
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


def main() -> None:
    browsers = discover_browsers()
    assert browsers, "No Chromium browser was found for the requested integration check."
    results = []
    for choice in browsers:
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
                results.append(
                    {
                        "browser": choice.name,
                        "windowsHost": choice.windows_host,
                        "platform": platform,
                        "pipeTransport": True,
                        "encryptedSession": True,
                        "studyWebsite": study_website(browser),
                    }
                )
            finally:
                browser.close()
    print(json.dumps({"wsl": is_wsl(), "browsers": results, "liveCampusRequests": False}))


if __name__ == "__main__":
    main()
