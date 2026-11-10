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
        page.set_default_timeout(10000)
        _ = page.goto(exercise_url + "#bfs/content", timeout=10000)
        outline = page.locator(".page-outline")
        expect(outline).to_be_visible()
        tab = page.get_by_role("tab", name="Flashcards · 3", exact=True).element_handle()
        link = page.get_by_role("link", name="Go deep, then return", exact=True).element_handle()
        stale_refresh = page.evaluate_handle(
            """async ([tab, link]) => {
                const outline = document.querySelector('.page-outline');
                const request = window.requestAnimationFrame;
                let refresh;
                window.requestAnimationFrame = callback => {
                    if (callback.name !== 'refresh') return request(callback);
                    refresh = callback;
                    return 0;
                };
                try {
                    tab.click();
                    await Promise.resolve();
                } finally {
                    window.requestAnimationFrame = request;
                }
                if (!refresh) throw new Error('The tab did not queue an outline refresh');
                link.click();
                return { outline, refresh };
            }""",
            [tab, link],
        )
        expect(page.get_by_role("heading", name="Go deep, then return", exact=True)).to_be_visible()
        expect(outline).to_be_visible()
        assert stale_refresh.evaluate("({ outline }) => !outline.isConnected")
        stale_refresh.evaluate("({ refresh }) => refresh(performance.now())")
        expect(outline).to_be_visible()
        expect(page.locator(".contents-toggle")).to_have_attribute("aria-expanded", "true")
        expect(outline).to_contain_text("Two orders, two behaviors")
    finally:
        context.close()
