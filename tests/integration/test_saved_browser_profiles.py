import os

import pytest
from browser_consumer_fixture import saved_profile_journey, synthetic_browser_keychain
from filelock import Timeout
from playwright.sync_api import Page, sync_playwright

from tum_mcp.browser_profiles import create_profile, profile_lock, remove_profile
from tum_mcp.commands import browser_profiles as manager
from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError, discover_browsers


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)
def test_saved_profile_survives_browser_restart_and_temporary_login_is_isolated() -> None:
    browsers = discover_browsers()
    assert browsers, "Install a Chromium browser for native profile verification."
    for browser in browsers:
        with browser_driver(browser), sync_playwright() as driver:
            saved_profile_journey(driver.chromium, browser)


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)
@pytest.mark.parametrize("close_browser", [False, True])
def test_manage_opens_profile_and_keeps_it_locked_until_its_windows_close(
    monkeypatch: pytest.MonkeyPatch,
    close_browser: bool,
) -> None:
    browser = discover_browsers()[0]
    selected = create_profile(browser, "Password settings")
    closed = []

    def close_window(page: Page, event: str, *, timeout: float) -> None:
        assert event == "close" and timeout == 0
        assert not page.is_closed()
        with pytest.raises(Timeout), profile_lock(selected):
            pytest.fail("An open profile was not locked")
        with page.expect_event("close", timeout=10000):
            if close_browser:
                browser = page.context.browser
                assert browser is not None
                browser.close()
            else:
                page.close()
        closed.append(True)

    monkeypatch.setattr(Page, "wait_for_event", close_window)
    monkeypatch.setattr(manager.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(manager, "discover_browsers", lambda: (browser,))

    def select(
        title: str, choices: tuple[tuple[BrowserChoice | manager.Action, str], ...]
    ) -> BrowserChoice | manager.Action:
        if closed:
            label = "Done"
        elif title == "Password settings":
            label = "Open"
        else:
            label = selected.login_label
        return next(value for value, text in choices if text == label)

    monkeypatch.setattr(manager, "choose", select)
    try:
        with synthetic_browser_keychain():
            manager.manage_browsers()
        assert closed == [True]
        with profile_lock(selected):
            pass
    except BrowserSetupError as error:
        raise AssertionError(
            "Synthetic profile window failed: " + error.message
        ) from error.__context__
    finally:
        remove_profile(selected)
