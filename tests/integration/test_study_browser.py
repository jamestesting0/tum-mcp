import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser
from playwright.sync_api import TimeoutError as BrowserTimeout
from pydantic import TypeAdapter
from study_browser_fixture import study_website

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def test_study_website_journeys_pass_in_the_checkout(course_browser: Browser) -> None:
    assert study_website(course_browser)["passed"]


def test_local_browser_preserves_defaults_and_disables_windows_port_randomization(
    course_browser: Browser,
) -> None:
    def flags(browser: Browser) -> tuple[str, set[str]]:
        session = browser.new_browser_cdp_session()
        try:
            arguments = TypeAdapter(tuple[str, ...]).validate_python(
                session.send("Browser.getBrowserCommandLine")["arguments"]
            )
        finally:
            session.detach()
        disabled = next(
            value.partition("=")[2].split(",")
            for value in reversed(arguments)
            if value.startswith("--disable-features=")
        )
        return arguments[0], set(disabled)

    executable, actual = flags(course_browser)
    with course_browser.new_context() as context:
        windows = context.new_page().evaluate("navigator.platform") == "Win32"
    with course_browser.browser_type.launch(
        executable_path=executable, headless=True, args=["--enable-automation"]
    ) as baseline:
        _, expected = flags(baseline)
    if windows:
        expected.add("TcpPortRandomizationWin")
    assert actual == expected


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
