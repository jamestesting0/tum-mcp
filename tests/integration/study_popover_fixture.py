"""Anchored notes preserve context, focus, keyboard behavior and viewport bounds."""

from playwright.sync_api import Page


def popover_checks(page: Page) -> None:
    popup = page.get_by_role("dialog", name="Comments", exact=True)
    assert page.locator(".content-comments, .view-actions, .content-tools").count() == 0
    for width in (320, 390, 800, 1440, 1920):
        page.set_viewport_size({"width": width, "height": 900})
        page.evaluate(
            "() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))"
        )
        if not popup.is_visible():
            page.locator(".comment-marker").first.click()
        page.wait_for_function("""() => {
          const p = document.querySelector('.comment-popover'), r = p.getBoundingClientRect();
          return p.matches(':popover-open') && r.width > 0 && r.left >= 11 && r.top >= 11
            && r.right <= innerWidth - 11 && r.bottom <= innerHeight - 11;
        }""")
        marker = page.locator(".comment-marker").first
        assert marker.evaluate(
            "e => {const r=e.getBoundingClientRect(); return r.width>=44 && r.height>=44;}"
        )
        assert marker.locator("svg").evaluate("e => e.getBoundingClientRect().width") == 16
        assert (
            marker.locator(".comment-marker-face").evaluate("e=>e.getBoundingClientRect().height")
            == 28
        )
    page.set_viewport_size({"width": 390, "height": 900})
    if not popup.is_visible():
        page.locator(".comment-marker").first.click()
    page.keyboard.press("Escape")
    popup.wait_for(state="hidden")
    assert page.evaluate("document.activeElement.matches('.comment-marker')")
    # Clicking the actual highlighted quote opens notes without a trip to the page end.
    point = page.evaluate("""() => {
      const range = [...CSS.highlights.get('study-comments')][0];
      range.startContainer.parentElement.scrollIntoView({block:'center'});
      const r = [...range.getClientRects()].find(rect => rect.width && rect.height);
      return {x:r.left+Math.min(10,r.width/2),y:r.top+r.height/2};
    }""")
    page.mouse.click(point["x"], point["y"])
    popup.wait_for(state="visible")
    page.get_by_role("button", name="Close comments", exact=True).click()
    assert page.evaluate("document.activeElement.matches('.comment-marker')")
    page.locator(".comment-marker").first.click()
    # Native outside click dismisses; its focus/scroll remains at the clicked content.
    page.locator("h1").click()
    popup.wait_for(state="hidden")
    page.locator(".comment-marker").first.click()
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    popup.wait_for(state="hidden")
    page.locator(".comment-marker").first.click()
    popup.wait_for(state="visible")
