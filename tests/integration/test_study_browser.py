import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser
from playwright.sync_api import TimeoutError as BrowserTimeout
from study_browser_fixture import study_website

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def test_study_website_journeys_pass_in_the_checkout(course_browser: Browser) -> None:
    assert study_website(course_browser)["passed"]


@pytest.mark.parametrize("missing", [None, "flashcards.mjs"])
def test_secondary_browser_smoke_loads_compiled_assets_and_rejects_missing_modules(
    course_browser: Browser, project: Path, missing: str | None
) -> None:
    from browser_consumer_fixture import study_smoke

    site = project / "study"
    if missing is not None:
        (site / missing).unlink()
        with pytest.raises((AssertionError, BrowserTimeout)):
            study_smoke(course_browser, site, "bfs")
    else:
        result = study_smoke(course_browser, site, "bfs")
        assert result["passed"]
        assert result["views"] == ["content", "flashcards", "practice"]
        assert result["widths"] == [390, 1440]
