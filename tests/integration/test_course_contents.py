"""Contents must follow the current page even when an old view still has queued work."""

import os

import pytest
import test_exercise_browser as fixtures
from playwright.sync_api import Browser, expect

exercise_url = fixtures.exercise_url

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Explicit owned browser QA."
)


def test_queued_contents_refresh_cannot_close_the_next_pages_outline(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = context.new_page()
        page.goto(exercise_url + "#bfs/content")
        expect(page.locator(".page-outline")).to_be_visible()
        # Hold frame callbacks while a panel mutation queues an outline refresh.
        page.evaluate("""() => {
            window.queuedFrames = [];
            window.originalFrame = requestAnimationFrame;
            window.requestAnimationFrame = callback => {
                queuedFrames.push(callback); return queuedFrames.length;
            };
        }""")
        page.get_by_role("tab", name="Flashcards · 3", exact=True).click()
        assert page.evaluate("queuedFrames.length > 0")
        page.get_by_role("link", name="Go deep, then return", exact=True).click()
        expect(page.get_by_role("heading", name="Go deep, then return", exact=True)).to_be_visible()
        expect(page.locator(".page-outline")).to_be_visible()
        # An already queued callback may run after the previous outline was aborted.
        page.evaluate("""() => {
            window.requestAnimationFrame = originalFrame;
            for (const callback of queuedFrames.splice(0)) callback(performance.now());
        }""")
        expect(page.locator(".page-outline")).to_be_visible()
        expect(page.locator(".contents-toggle")).to_have_attribute("aria-expanded", "true")
        expect(page.locator(".page-outline")).to_contain_text("Two orders, two behaviors")
    finally:
        context.close()
