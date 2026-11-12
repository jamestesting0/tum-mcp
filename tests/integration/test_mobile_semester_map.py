import json
import os
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from documents import content_file
from material_fixture import exam_document, exam_project
from playwright.sync_api import expect

from tum_mcp.course.app.build import build
from tum_mcp.course.app.preview import Handler, PreviewServer

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Owned browser QA."
)


@pytest.fixture(scope="module")
def map_site(tmp_path_factory):
    root = exam_project(tmp_path_factory.mktemp("mobile-semester-map"))
    (root / "app").mkdir()
    document = exam_document(root)
    next(concept for concept in document["concepts"] if concept["key"] == "decorator")["title"] = (
        r"Decorator with a long component interface \(X_{1}\) and nested responsibilities"
    )
    document["links"].append({"start": "loose-coupling", "end": "decorator", "kind": "requires"})
    content_file(root, "exam").write_text(json.dumps(document))
    build(root, publish=False)
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(root / "app"))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)


def camera(page) -> tuple[float, float, float]:
    x, y, width, height = map(float, page.locator(".exam-map-svg").get_attribute("viewBox").split())
    return (
        x + width / 2,
        y + height / 2,
        float(page.locator(".exam-map-scroll").get_attribute("data-scale")),
    )


def test_desktop_map_preserves_compact_controls_and_free_pan_zoom(course_browser, map_site):
    with course_browser.new_context(viewport={"width": 1440, "height": 900}) as context:
        page = context.new_page()
        page.goto(map_site + "#exam/sheet")
        expect(page.get_by_role("button", name="Fit", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Full screen", exact=True)).to_be_visible()
        expect(page.locator(".exam-map-topic-select")).to_have_count(0)
        expect(page.locator(".exam-map-move")).to_have_count(0)
        expect(page.locator(".exam-map-overview")).to_be_hidden()
        tools = page.locator(".exam-map-frame .exam-map-tools")
        assert tools.evaluate("el => getComputedStyle(el).position") == "absolute"
        canvas = page.locator(".exam-map-scroll")
        canvas.focus()
        before = page.locator(".exam-map-svg").get_attribute("viewBox")
        page.keyboard.press("ArrowLeft")
        assert page.locator(".exam-map-svg").get_attribute("viewBox") != before
        before = float(page.locator(".exam-map-svg").get_attribute("viewBox").split()[2])
        page.get_by_role("button", name="Zoom out", exact=True).click()
        assert float(page.locator(".exam-map-svg").get_attribute("viewBox").split()[2]) > before


@pytest.mark.parametrize(
    "width,height",
    [(320, 568), (390, 844), (844, 390), (719, 900), (720, 900), (768, 1024), (1440, 900)],
)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_semester_graph_is_visible_readable_and_keeps_one_surface(
    course_browser,
    map_site,
    tmp_path: Path,
    width: int,
    height: int,
    theme: str,
) -> None:
    with course_browser.new_context(
        viewport={"width": width, "height": height}, color_scheme=theme
    ) as context:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(map_site + "#exam/sheet")
        expect(page.locator(".exam-map-svg")).to_be_visible()
        page.wait_for_function("document.querySelector('.exam-map-scroll').dataset.scale")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        usable = page.locator('.exam-node[tabindex="0"]')
        assert usable.count() > 0
        metrics = usable.evaluate_all("""nodes => nodes.map(node => {
            const box=node.getBoundingClientRect();
            return {width:box.width, height:box.height,
                font:parseFloat(getComputedStyle(node.querySelector('text')).fontSize),
                scale:node.getScreenCTM().a, viewBox:node.ownerSVGElement.getAttribute('viewBox')};
        })""")
        assert all(
            item["width"] >= (44 if width < 720 else 36)
            and item["height"] >= (44 if width < 720 else 36)
            and item["font"] * item["scale"] >= (13.95 if width < 720 else 9.65)
            for item in metrics
        ), metrics
        before_fit = camera(page)[2]
        page.get_by_role("button", name="Fit", exact=True).click()
        assert camera(page)[2] <= before_fit
        page.get_by_role("button", name="Zoom in", exact=True).click()
        page.get_by_role("button", name="Zoom out", exact=True).click()
        page.locator('.exam-node[data-concept="loose-coupling"]').focus()
        page.keyboard.press("Enter")
        card = page.locator(".exam-map-card")
        expect(card).to_contain_text("Depend on interfaces")
        page.screenshot(path=str(tmp_path / f"map-inline-{width}-{height}-{theme}.png"))
        handle = page.locator(".exam-map-svg").element_handle()
        trigger = page.get_by_role("button", name="Full screen", exact=True)
        trigger.scroll_into_view_if_needed()
        reading = page.evaluate("[scrollY, document.querySelector('main').scrollTop]")
        page.locator(".exam-map").evaluate("el => el.requestFullscreen = undefined")
        trigger.click()
        dialog = page.get_by_role("dialog", name="Semester map", exact=True)
        expect(dialog).to_be_visible()
        assert handle.evaluate("svg => svg === document.querySelector('.exam-map-svg')")
        assert page.locator(".exam-map-svg").count() == 1
        page.get_by_role("button", name="Zoom in", exact=True).click()
        canvas = page.locator(".exam-map-scroll")
        canvas.focus()
        before_move = camera(page)
        page.keyboard.press("ArrowRight")
        assert camera(page) != before_move
        page.get_by_role("button", name="Fit", exact=True).click()
        assert card.evaluate("el => el.scrollHeight >= el.clientHeight")
        if width in {390, 1440} or height == 390:
            page.screenshot(path=str(tmp_path / f"map-workspace-{width}-{height}-{theme}.png"))
        page.keyboard.press("Escape")
        expect(card).to_be_hidden()
        expect(dialog).to_be_visible()
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(trigger).to_be_focused()
        assert handle.evaluate("svg => svg === document.querySelector('.exam-map-svg')")
        assert page.evaluate("[scrollY, document.querySelector('main').scrollTop]") == reading
        trigger.click()
        page.evaluate("location.hash = '#exam'")
        expect(page.locator("dialog.exam-map-modal")).to_have_count(0)
        page.set_viewport_size({"width": width + 1, "height": height})
        expect(page.locator(".exam-map-svg")).to_have_count(0)
        assert not handle.evaluate("svg => svg.isConnected")
        assert page.evaluate("document.documentElement.style.overflow !== 'hidden'")
        assert errors == []


def touch(session, kind, points) -> None:
    session.send(
        "Input.dispatchTouchEvent",
        {
            "type": kind,
            "touchPoints": [
                {"x": x, "y": y, "id": identifier, "radiusX": 2, "radiusY": 2, "force": 1}
                for identifier, x, y in points
            ],
        },
    )


def test_real_chromium_touch_preserves_inline_scroll_and_expanded_pan_pinch(
    course_browser, map_site
) -> None:
    with course_browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    ) as context:
        page = context.new_page()
        page.goto(map_site + "#exam/sheet")
        canvas = page.locator(".exam-map-scroll")
        expect(canvas).to_be_visible()
        page.wait_for_function("document.querySelector('.exam-map-scroll').dataset.scale")
        box = canvas.bounding_box()
        session = context.new_cdp_session(page)
        x, y = box["x"] + box["width"] / 2, box["y"] + 170
        before_horizontal = camera(page)
        touch(session, "touchStart", [(0, x, y)])
        touch(session, "touchMove", [(0, x - 70, y)])
        touch(session, "touchEnd", [])
        assert camera(page) != before_horizontal
        before_view = camera(page)
        before_scroll = page.evaluate("scrollY + document.querySelector('main').scrollTop")
        touch(session, "touchStart", [(1, x, y)])
        for index in range(1, 7):
            touch(session, "touchMove", [(1, x, y - index * 20)])
        touch(session, "touchEnd", [])
        page.wait_for_function(
            "value => scrollY + document.querySelector('main').scrollTop > value + 20",
            arg=before_scroll,
        )
        assert camera(page) == before_view
        expect(page.locator(".exam-node.selected")).to_have_count(0)
        page.get_by_role("button", name="Full screen", exact=True).click()
        expect(page.get_by_role("dialog", name="Semester map")).to_be_visible()
        box = canvas.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        before = camera(page)
        locked_scroll = page.evaluate("scrollY + document.querySelector('main').scrollTop")
        touch(session, "touchStart", [(2, x, y)])
        touch(session, "touchMove", [(2, x - 80, y + 10)])
        touch(session, "touchEnd", [])
        assert camera(page) != before
        before = camera(page)
        page.evaluate("""window.nativeContacts = new Set();
            document.addEventListener('pointerdown',
                e => window.nativeContacts.add(e.pointerId), true);
            document.addEventListener('pointerup',
                e => window.nativeContacts.delete(e.pointerId), true);""")
        touch(session, "touchStart", [(3, x - 25, y), (4, x + 25, y)])
        touch(session, "touchMove", [(3, x - 60, y), (4, x + 60, y)])
        assert camera(page)[2] > before[2]
        # CDP ends all contacts on touchEnd. Inject only the one-contact release;
        # movement before and after it still comes from the native touch device.
        canvas.evaluate("""element => element.dispatchEvent(new PointerEvent('pointerup', {
            pointerId:[...window.nativeContacts][1], pointerType:'touch', bubbles:true
        }))""")
        before = camera(page)
        before_box = page.locator(".exam-map-svg").get_attribute("viewBox")
        touch(session, "touchMove", [(3, x - 10, y + 40)])
        page.wait_for_function(
            "box => document.querySelector('.exam-map-svg').getAttribute('viewBox') !== box",
            arg=before_box,
        )
        assert camera(page) != before
        touch(session, "touchCancel", [])
        page.get_by_role("button", name="Fit", exact=True).click()
        target = page.locator('.exam-node[tabindex="0"]').first
        node_box, frame = target.bounding_box(), canvas.bounding_box()
        px = (
            max(node_box["x"], frame["x"])
            + min(node_box["x"] + node_box["width"], frame["x"] + frame["width"])
        ) / 2
        py = (
            max(node_box["y"], frame["y"])
            + min(node_box["y"] + node_box["height"], frame["y"] + frame["height"])
        ) / 2
        page.touchscreen.tap(px, py)
        expect(page.locator(".exam-map-card")).to_be_visible()
        assert page.evaluate("scrollY + document.querySelector('main').scrollTop") == locked_scroll
        page.get_by_role("button", name="Exit full screen", exact=True).click()
        session.detach()


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_MOBILE_MAP_WEBKIT") != "1", reason="Explicit WebKit source lane."
)
def test_webkit_map_tap_controls_dialog_and_resize(map_site, course_playwright) -> None:
    with course_playwright.webkit.launch() as browser:
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
            page.goto(map_site + "#exam/sheet")
            expect(page.locator(".exam-map-svg")).to_be_visible()
            page.get_by_role("button", name="Full screen", exact=True).click()
            expect(page.get_by_role("dialog", name="Semester map")).to_be_visible()
            page.get_by_role("button", name="Zoom in", exact=True).click()
            page.set_viewport_size({"width": 844, "height": 390})
            page.get_by_role("button", name="Fit", exact=True).click()
            page.get_by_role("button", name="Exit full screen", exact=True).click()
            expect(page.get_by_role("button", name="Full screen", exact=True)).to_be_focused()
            expect(page.locator(".exam-map-svg")).to_be_visible()
        finally:
            browser.close()
