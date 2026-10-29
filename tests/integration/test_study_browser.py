import os

import pytest
from playwright.sync_api import Browser
from study_browser_fixture import study_website

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def test_study_website_journeys_pass_in_the_checkout(course_browser: Browser) -> None:
    assert study_website(course_browser)["passed"]
