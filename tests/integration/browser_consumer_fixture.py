# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run through: npm run test:consumer -- /path/to/package.tgz
# The controller supplies the isolated, installed backend interpreter.
"""Owned-browser verification with synthetic data and no live campus requests."""

import json
import sys
import time

from playwright.sync_api import Route, sync_playwright

from tum_moodle.auth import Cookie, Session, SessionStore
from tum_moodle.browser_runtime import browser_driver
from tum_moodle.browsers import discover_browsers, is_wsl
from tum_moodle.config import Paths

HTML = """<!doctype html><title>Synthetic local sign-in</title>
<button onclick="document.cookie='MoodleSession=synthetic-browser-only; path=/; secure';
document.querySelector('output').textContent='Signed in';">Sign in fixture</button>
<output></output>"""


def fixture(route: Route) -> None:
    assert route.request.url.startswith("https://fixture.invalid/")
    route.fulfill(status=200, content_type="text/html", body=HTML)


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
                    }
                )
            finally:
                browser.close()
    print(json.dumps({"wsl": is_wsl(), "browsers": results, "liveCampusRequests": False}))


if __name__ == "__main__":
    main()
