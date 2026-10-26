"""Real local reading/navigation journeys for all prepared workspace subsets."""

import json
import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
import test_exercise_browser as browser_fixtures
import test_lecture_build as lecture_fixtures
from playwright.sync_api import Browser, expect
from test_exercise_browser import switch_workspace

from tum_mcp.study_build import build
from tum_mcp.study_preview import Handler, PreviewServer

course_browser = browser_fixtures.course_browser
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
def test_notes_deep_links_figure_and_workspace_return(
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
        expect(page.get_by_role("heading", name="Lecture Notes", exact=True)).to_be_visible()
        directory = Path(os.environ.get("TUM_MCP_LECTURE_QA_PATH", str(tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(directory / f"{width}-{theme}-list.png"))
        page.locator(".topic-row a").click()
        expect(page.locator(".lecture-section h2")).to_have_text(
            "Why first discovery gives a shortest path"
        )
        assert page.locator(".lecture-times a").get_attribute("href").endswith("?t=20")
        figure = page.get_by_role("img")
        expect(figure).to_be_visible()
        assert page.locator(".lecture-figure .lecture-time").get_attribute("href").endswith("?t=37")
        assert page.locator(".lecture-image").get_attribute("target") == "_blank"
        page.wait_for_function(
            "() => { const image = document.querySelector('.lecture-figure img');"
            "return image.complete && image.naturalWidth === 640; }"
        )
        page.screenshot(path=str(directory / f"{width}-{theme}-reading.png"))
        page.locator(".lecture-image").focus()
        expect(page.locator(".lecture-image")).to_be_focused()
        page.screenshot(path=str(directory / f"{width}-{theme}-figure-focus.png"))
        assert page.locator(".tabs,.home-reset,.review-toggle").count() == 0
        assert "AI-added" not in page.locator("main").inner_text()
        page.evaluate("location.hash = '#lectures/bfs-lecture/fifo-invariant'")
        expect(page.locator(".lecture-section h2")).to_be_focused()
        page.reload()
        expect(page.locator(".lecture-section")).to_be_visible()
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        switch_workspace(page, "Lecture Notes")
        expect(page.locator(".lecture-section")).to_be_visible()
        page.go_back()
        expect(page.get_by_role("heading", name="Exercises", exact=True)).to_be_visible()
        page.go_forward()
        expect(page.locator(".lecture-section")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == external == []
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
            label = {"study": "Study", "exercises": "Exercises", "lectures": "Lecture Notes"}
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
    content["lectures"][0]["sections"][0]["figures"][0]["caption"] = (
        '<script>alert("unsafe")</script>'
    )
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
            expect(page.get_by_text("That section is no longer here.", exact=False)).to_be_visible()
            expect(page.get_by_text("This image could not load.", exact=False)).to_be_visible()
            expect(page.locator(".lecture-meta")).to_contain_text("Partial notes")
            assert (
                page.locator("figcaption")
                .inner_text()
                .startswith('<script>alert("unsafe")</script>')
            )
            assert page.locator("main script").count() == 0
            page.goto(url + "#lectures/%E0%A4%A")
            expect(page.get_by_text("That lecture is no longer here.", exact=False)).to_be_visible()
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=3)
