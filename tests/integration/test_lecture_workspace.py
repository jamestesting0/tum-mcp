"""Real local reading/navigation journeys for all prepared workspace subsets."""

import json
import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
import test_lecture_build as lecture_fixtures
from playwright.sync_api import Browser, expect
from test_exercise_browser import switch_workspace

from tum_mcp.study_build import build
from tum_mcp.study_preview import Handler, PreviewServer

lecture_project = lecture_fixtures.lecture_project

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Explicit owned browser QA."
)


@pytest.fixture
def lecture_url(lecture_project: Path) -> Iterator[str]:
    build(lecture_project, publish=False)
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(lecture_project / "study"))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


@pytest.mark.parametrize(
    "width,theme", [(390, "light"), (390, "dark"), (1440, "light"), (1440, "dark")]
)
def test_highlights_deep_links_thumbnails_and_workspace_return(
    course_browser: Browser, lecture_url: str, width: int, theme: str, tmp_path: Path
) -> None:
    context = course_browser.new_context(
        viewport={"width": width, "height": 844}, color_scheme=theme
    )
    errors, external = [], []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request",
        lambda request: (
            external.append(request.url) if not request.url.startswith(lecture_url) else None
        ),
    )
    try:
        page.goto(lecture_url + "#lectures")
        expect(page.get_by_role("heading", name="Lecture", exact=True)).to_be_visible()
        expect(page.locator(".topic-row .lecture-count")).to_have_text(
            "1 note \u00b7 2 highlights \u00b7 2 min of 10 min"
        )
        directory = Path(os.environ.get("TUM_MCP_LECTURE_QA_PATH", str(tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(directory / f"{width}-{theme}-list.png"))
        page.locator(".topic-row a").click()
        titles = [
            "Why first discovery gives a shortest path",
            "Mark a vertex when it enters the queue",
        ]
        expect(page.locator(".lecture-highlight h3")).to_have_text(titles)
        expect(page.locator(".lecture-note-text")).to_contain_text("both endpoints")
        assert page.locator(".lecture-note img,.lecture-note .lecture-when").count() == 0
        assert "Keep in mind" not in page.locator("main").inner_text()
        # Each highlight shows its range and length; the frame opens the same moment.
        first = page.locator(".lecture-highlight").first
        time_link = first.locator(".lecture-when .lecture-time")
        expect(time_link).to_have_text("0:20\u20131:00")
        expect(first.locator(".lecture-when")).to_contain_text("40 s")
        assert time_link.get_attribute("href").endswith("?t=20")
        assert time_link.inner_text() in time_link.get_attribute("aria-label")
        thumb = first.locator(".lecture-thumb")
        assert thumb.get_attribute("href") == time_link.get_attribute("href")
        assert thumb.get_attribute("tabindex") == "-1"
        assert thumb.get_attribute("aria-hidden") == "true"
        page.wait_for_function(
            "() => [...document.querySelectorAll('.lecture-thumb img')]"
            ".every(image => image.complete && image.naturalWidth === 640)"
        )
        # Slide pages sit in the highlight's sources; the recording is the time link.
        first.locator(".citation summary").click()
        expect(first.locator(".citation[open] .citation-locator")).to_have_text("p. 2")
        page.keyboard.press("Escape")
        assert page.locator(".lecture-highlight").nth(1).locator(".citation").count() == 0
        page.evaluate("""async () => {
          document.activeElement.blur();
          window.scrollTo(0, 0);
          await new Promise(requestAnimationFrame);
        }""")
        page.screenshot(path=str(directory / f"{width}-{theme}-reading.png"), full_page=True)
        # Contents is docked on wide screens and opens over the page elsewhere.
        outline, title = page.locator(".page-outline"), titles[1]
        contents = page.locator(".contents-toggle")
        if width < 1200:
            expect(outline).to_be_hidden()
            contents.click()
        expect(contents).to_have_attribute("aria-expanded", "true")
        outline.get_by_role("link", name=title, exact=True).click()
        expect(page.get_by_role("heading", name=title, exact=True)).to_be_focused()
        expect(outline.locator("[aria-current]")).to_have_text(title)
        if width < 1200:
            expect(outline).to_be_hidden()
        assert page.locator(".tabs,.home-reset,.review-toggle").count() == 0
        assert "AI-added" not in page.locator("main").inner_text()
        page.evaluate("location.hash = '#lectures/bfs-lecture/h-second'")
        expect(page.locator('[data-lecture-section="h-second"] h3')).to_be_focused()
        page.reload()
        expect(page.locator(".lecture-highlight").first).to_be_visible()
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        switch_workspace(page, "Lecture")
        expect(page.locator(".lecture-highlight").first).to_be_visible()
        page.go_back()
        expect(page.get_by_role("heading", name="Exercises", exact=True)).to_be_visible()
        page.go_forward()
        expect(page.locator(".lecture-highlight").first).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == external == []
    finally:
        context.close()


@pytest.mark.parametrize("kind", ["notes", "highlights", "empty"])
@pytest.mark.parametrize("width,theme", [(390, "light"), (1440, "dark")])
def test_notes_only_highlights_only_and_empty_selection(
    course_browser: Browser,
    lecture_url: str,
    lecture_project: Path,
    kind: str,
    width: int,
    theme: str,
    tmp_path: Path,
) -> None:
    path = lecture_project / "study/lectures.json"
    value = json.loads(path.read_bytes())
    lecture = value["lectures"][0]
    if kind == "notes":
        first = lecture["highlights"][0]
        lecture["notes"][0]["image"] = first["thumbnail"] | {"alt": "A path from A to B to C."}
        lecture["notes"][0]["evidence"] += first["evidence"]
    if kind != "notes":
        lecture["notes"] = []
    if kind != "highlights":
        lecture["highlights"] = []
    used = {key for item in lecture["notes"] + lecture["highlights"] for key in item["evidence"]}
    value["evidence"] = [item for item in value["evidence"] if item["key"] in used]
    path.write_text(json.dumps(value))
    build(lecture_project, publish=False)
    context = course_browser.new_context(
        viewport={"width": width, "height": 844}, color_scheme=theme
    )
    try:
        page = context.new_page()
        page.goto(lecture_url + "#lectures/bfs-lecture")
        expect(page.locator(".lecture-note")).to_have_count(1 if kind == "notes" else 0)
        expect(page.locator(".lecture-highlight")).to_have_count(2 if kind == "highlights" else 0)
        if kind == "notes":
            image = page.get_by_role("img", name="A path from A to B to C.")
            expect(image).to_be_visible()
            image.evaluate("image => image.decode()")
            assert page.locator(".lecture-when,.lecture-thumb").count() == 0
            page.locator(".lecture-note .citation summary").click()
            expect(page.locator(".lecture-note .citation .lecture-time")).to_have_attribute(
                "href", "https://example.invalid/lectures/synthetic?t=20"
            )
            page.keyboard.press("Escape")
            page.evaluate("location.hash = '#lectures/bfs-lecture/n-adjacency'")
            expect(page.locator(".lecture-note")).to_be_focused()
        elif kind == "empty":
            expect(
                page.get_by_text(
                    "No additional notes or highlights were selected from this lecture.", exact=True
                )
            ).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        folder = Path(os.environ.get("TUM_MCP_LECTURE_QA_PATH", str(tmp_path)))
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / f"{kind}-{width}-{theme}.png"), full_page=True)
    finally:
        context.close()


@pytest.mark.parametrize(
    "selected",
    [
        ("study",),
        ("exercises",),
        ("lectures",),
        ("study", "exercises"),
        ("study", "lectures"),
        ("exercises", "lectures"),
        ("study", "exercises", "lectures"),
    ],
)
def test_all_workspace_subsets_route_without_two_way_fallthrough(
    lecture_project: Path, course_browser: Browser, selected: tuple[str, ...]
) -> None:
    for workspace, filename in (
        ("study", "content.json"),
        ("exercises", "exercises.json"),
        ("lectures", "lectures.json"),
    ):
        if workspace not in selected:
            (lecture_project / "study" / filename).unlink()
    build(lecture_project, publish=False)
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(lecture_project / "study"))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        context = course_browser.new_context()
        try:
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            label = {"study": "Study", "exercises": "Exercises", "lectures": "Lecture"}
            for workspace in selected:
                if len(selected) > 1:
                    switch_workspace(page, label[workspace])
                assert page.locator("main h1").inner_text() != "Course unavailable"
                assert page.locator(".workspace-name").inner_text() == label[workspace]
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=3)


def test_missing_routes_images_and_untrusted_copy_are_readable(
    lecture_project: Path, course_browser: Browser
) -> None:
    path = lecture_project / "study/lectures.json"
    content = json.loads(path.read_text())
    content["lectures"][0]["highlights"][0]["teaches"] = '<script>alert("unsafe")</script>'
    content["lectures"][0]["coverage"]["status"] = "partial"
    path.write_text(json.dumps(content))
    build(lecture_project, publish=False)
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(lecture_project / "study"))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        context = course_browser.new_context()
        try:
            page = context.new_page()
            page.route("**/lecture-assets/*.png", lambda route: route.abort())
            url = f"http://127.0.0.1:{server.server_port}/"
            page.goto(url + "#lectures/bfs-lecture/missing")
            expect(
                page.get_by_text("That lecture passage is no longer here.", exact=True)
            ).to_be_visible()
            # A frame that cannot load disappears; the highlight's text stays.
            expect(page.locator(".lecture-thumb").first).to_be_hidden()
            expect(page.locator(".lecture-thumb").nth(1)).to_be_hidden()
            expect(page.locator(".lecture-meta")).to_contain_text("Partial coverage")
            expect(page.locator(".lecture-teaches").first).to_have_text(
                '<script>alert("unsafe")</script>'
            )
            assert page.locator("main script").count() == 0
            page.goto(url + "#lectures/%E0%A4%A")
            expect(page.get_by_text("That lecture is no longer here.", exact=False)).to_be_visible()
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=3)
