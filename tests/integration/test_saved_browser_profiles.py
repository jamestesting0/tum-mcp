import os

import pytest
from browser_consumer_fixture import saved_profile_journey
from playwright.sync_api import sync_playwright

from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import discover_browsers


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
