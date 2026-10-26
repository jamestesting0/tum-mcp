"""A few real student journeys; logic edges are not multiplied by every viewport."""

import json
import os
import re
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import discover_browsers
from tum_mcp.study_build import build
from tum_mcp.study_preview import Handler, PreviewServer
from tum_mcp.study_publish_site import export_site

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def switch_workspace(page: Page, name: str) -> None:
    """Use the same footer on desktop and in the mobile outline."""
    page.locator(".outline-toggle").wait_for(state="visible")
    expand = page.get_by_role("button", name="Expand course outline", exact=True)
    if expand.is_visible():
        expand.click()
    page.locator(".workspace-trigger").click()
    page.get_by_role("menuitemradio", name=name, exact=True).click()
    expect(page.locator(".workspace-trigger")).to_have_attribute(
        "aria-label", "Switch workspace, " + name
    )


@pytest.fixture(scope="module")
def course_browser() -> Iterator[Browser]:
    choices = discover_browsers()
    assert choices, "The requested browser QA requires an existing Chromium browser."
    with browser_driver(choices[0]), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=choices[0].executable, headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def exercise_url(exercise_project: Path) -> Iterator[str]:
    build(exercise_project, publish=False)
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(exercise_project / "study"))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


@pytest.mark.parametrize("width", [390, 1440])
def test_optional_guidance_and_workspace_round_trip(
    course_browser: Browser, exercise_url: str, width: int, tmp_path: Path
) -> None:
    # Given a generated combined course, in an isolated browser context.
    context = course_browser.new_context(viewport={"width": width, "height": 900})
    try:
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(exercise_url)
        # When working independently, then requesting only the help that is useful.
        switch_workspace(page, "Exercises")
        page.get_by_role("heading", name="Exercises", exact=True).wait_for()
        page.set_default_timeout(2000)
        page.get_by_role("link", name=re.compile("Exercise 1.*Improve a tentative")).filter(
            visible=True
        ).first.click()
        expect(page.get_by_role("heading", name="The problem", exact=True)).to_be_visible()
        page.get_by_text("Guidance", exact=True).click()
        response = page.get_by_label("Your answer", exact=True)
        response.fill("1")
        page.get_by_role("button", name="Check", exact=True).click()
        expect(page.get_by_text("Include the cost of reaching A", exact=False)).to_be_visible()
        page.get_by_role("button", name="Hint", exact=True).click()
        expect(
            page.locator("#content").get_by_text("A path cost includes all edges", exact=False)
        ).to_be_visible()
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        assert page.get_by_label("Your answer", exact=True).input_value() == "1"
        page.get_by_label("Your answer", exact=True).fill("3")
        page.get_by_role("button", name="Check", exact=True).click()
        page.get_by_role("button", name="Continue", exact=True).click()
        prompt = page.get_by_role(
            "heading", name="Why does this replace d(B)? You can work on paper.", exact=True
        )
        expect(prompt).to_be_focused()
        position = prompt.bounding_box()
        assert position is not None and 0 <= position["y"] < 900
        if width >= 800:
            assert page.evaluate("scrollY === 0")
            footer = page.locator(".sidebar-footer").bounding_box()
            assert footer and 800 < footer["y"] + footer["height"] <= 900
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(
            page.get_by_text("Replace 5 with 3 because 3 is cheaper.", exact=False)
        ).to_be_visible()
        page.get_by_text("Solution", exact=True).click()
        expect(page.get_by_role("heading", name="Worked solution", exact=True)).to_be_visible()
        # Then no extra mode/form is required and the existing reading layout stays usable.
        assert errors == []
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        directory = Path(os.environ.get("TUM_MCP_EXERCISE_QA_PATH", str(tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(directory / f"{width}-guided-solution.png"))
    finally:
        context.close()


def test_changed_answers_repeat_clicks_and_reload_preserve_honest_feedback(
    course_browser: Browser, exercise_url: str
) -> None:
    # Given a numeric step in an isolated learning session.
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/candidate")
        answer = page.get_by_label("Your answer", exact=True)
        # When checking, editing and retrying, the previous verdict cannot remain attached.
        answer.fill("3")
        page.get_by_role("button", name="Check", exact=True).click()
        expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
        answer.fill("4")
        expect(page.get_by_text("Checked correct", exact=True)).not_to_be_visible()
        answer.fill("1 + 2")
        expect(page.get_by_role("button", name="Check", exact=True)).to_be_disabled()
        expect(page.get_by_text("Use a finite decimal number", exact=False)).to_be_visible()
        answer.fill("3")
        page.get_by_role("button", name="Check", exact=True).dblclick()
        expect(
            page.get_by_role("heading", name="What is the cost through A?", exact=True)
        ).to_be_visible()
        answer.fill("1")
        switch_workspace(page, "Exercises")
        expect(answer).to_have_value("1")
        page.reload()
        # Then repeated activation did not advance and the draft survives a real reload.
        expect(page.get_by_label("Your answer", exact=True)).to_have_value("1")
    finally:
        context.close()


def test_paper_only_review_and_direct_solution_do_not_require_a_form(
    course_browser: Browser, exercise_url: str
) -> None:
    # Given a proof exercise whose student may work entirely on paper.
    context = course_browser.new_context(viewport={"width": 390, "height": 900})
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/sheet-1/sample-minimum-proof")
        # When reviewing independently, recording review and asking for the solution.
        page.get_by_role("button", name="Mark reviewed", exact=True).click()
        expect(page.get_by_role("button", name="Reviewed", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        page.get_by_role("button", name="Expand course outline", exact=True).click()
        expect(page.get_by_role("link", name=re.compile("Exercise 2.*Reviewed"))).to_be_visible()
        page.get_by_role("button", name="Collapse course outline", exact=True).press("Escape")
        page.get_by_text("Solution", exact=True).click()
        expect(page.get_by_role("heading", name="Worked proof", exact=True)).to_be_visible()
        page.get_by_text("Guidance", exact=True).click()
        page.get_by_role("button", name="Compare", exact=True).click()
        # Then comparison is available with no typed response or automatic correctness claim.
        expect(page.get_by_label("Your answer", exact=True)).not_to_be_visible()
        expect(page.get_by_text("The minimum-choice rule says", exact=False)).to_be_visible()
        expect(page.get_by_text("Checked correct", exact=True)).not_to_be_visible()
    finally:
        context.close()


def test_choice_feedback_revision_recovery_and_workspace_reset(
    course_browser: Browser, exercise_url: str, exercise_project: Path
) -> None:
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.goto(exercise_url + "#bfs/flashcards")
        page.locator(".flashcard").click()
        page.locator('[data-card-action="got"]').click()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/transfer-choice")
        page.get_by_label("Replace with 6", exact=True).check()
        page.get_by_role("button", name="Check", exact=True).click()
        expect(
            page.get_by_text("Include the cost of reaching the neighbor", exact=False)
        ).to_be_visible()
        page.get_by_label("Keep 8", exact=True).check()
        expect(page.get_by_text("Check your reasoning", exact=True)).not_to_be_visible()
        page.get_by_role("button", name="Check", exact=True).click()
        page.get_by_role("button", name="Finish", exact=True).click()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/candidate")
        page.get_by_label("Your answer", exact=True).fill("old draft")
        path = exercise_project / "study/exercises.json"
        payload = json.loads(path.read_bytes())
        payload["sets"][0]["exercises"][0]["steps"][0]["prompt"] += " Explain the path cost."
        path.write_text(json.dumps(payload))
        build(exercise_project, publish=False)
        page.reload()
        expect(page.get_by_label("Your answer", exact=True)).to_have_value("")
        expect(page.get_by_text("Exercise updated · previous responses", exact=True)).to_have_count(
            0
        )
        assert page.evaluate("""() => Object.keys(localStorage)
            .filter(key => key.startsWith('course-exercises:'))
            .some(key => { const saved = JSON.parse(localStorage.getItem(key));
                return saved?.steps?.candidate?.draft === 'old draft'; })""")
        page.get_by_label("Your answer", exact=True).fill("new draft")
        page.reload()
        expect(page.get_by_text("Exercise updated · previous responses", exact=True)).to_have_count(
            0
        )
        assert page.evaluate("""() => Object.keys(localStorage)
            .filter(key => key.startsWith('course-exercises:'))
            .some(key => { const saved = JSON.parse(localStorage.getItem(key));
                return saved?.steps?.candidate?.draft === 'old draft'; })""")
        page.evaluate("localStorage.setItem('study-space:other-course:progress:v1', 'keep')")
        page.locator(".course-title").click()
        page.get_by_role("button", name="Reset exercise progress", exact=True).click()
        page.get_by_role("button", name="Reset", exact=True).click()
        assert (
            page.evaluate("localStorage.getItem('study-space:other-course:progress:v1')") == "keep"
        )
        assert (
            page.evaluate(
                "Object.keys(localStorage)"
                ".filter(key => key.startsWith('course-exercises:')).length"
            )
            == 0
        )
        page.goto(exercise_url + "#bfs/flashcards")
        page.reload()
        page.locator(".flashcard").click()
        expect(page.locator('[data-card-action="got"]')).to_have_attribute("aria-pressed", "true")
    finally:
        context.close()


def test_exercise_passage_comment_saves_privately_and_survives_reload(
    course_browser: Browser, exercise_url: str, exercise_project: Path
) -> None:
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation")
        page.locator('[data-field="statement:0"] p').first.evaluate("""element => {
            const range = document.createRange(); range.selectNodeContents(element);
            getSelection().removeAllRanges(); getSelection().addRange(range);
        }""")
        page.keyboard.press("Control+Alt+m")
        page.get_by_role("textbox", name="Comment", exact=True).fill(
            "Explain why discovery is not final."
        )
        page.get_by_role("button", name="Save", exact=True).click()
        marker = page.get_by_role("button", name=re.compile("1 comment on"))
        expect(marker).to_be_visible()
        page.reload()
        expect(marker).to_be_visible()
        document = json.loads((exercise_project / ".tum-mcp/comments.json").read_bytes())
        assert document["schema_version"] == 2
        assert document["comments"][0]["anchor"]["exercise_key"] == "sample-relaxation"
        assert "Explain why discovery" not in (exercise_project / "study/data.mjs").read_text()
    finally:
        context.close()


def test_blocked_storage_keeps_the_current_session_usable(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context()
    try:
        context.add_init_script("""Storage.prototype.setItem = function () {
            throw new DOMException('Synthetic quota', 'QuotaExceededError');
        };""")
        page = context.new_page()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/candidate")
        page.get_by_label("Your answer", exact=True).fill("3")
        page.get_by_role("button", name="Check", exact=True).click()
        expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
        expect(page.get_by_text("Progress cannot be saved", exact=False)).to_be_visible()
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        expect(page.get_by_label("Your answer", exact=True)).to_have_value("3")
    finally:
        context.close()


def test_missing_course_data_offers_recovery_instead_of_loading_forever(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.route("**/data.mjs", lambda route: route.abort())
        page.goto(exercise_url)
        expect(page.get_by_role("heading", name="Course unavailable", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Reload course", exact=True)).to_be_visible()
    finally:
        context.close()


@pytest.mark.parametrize("missing", ["study", "exercises"])
def test_unprepared_workspace_has_a_path_back_to_prepared_content(
    course_browser: Browser, exercise_project: Path, missing: str
) -> None:
    filename = "content.json" if missing == "study" else "exercises.json"
    (exercise_project / "study" / filename).unlink()
    build(exercise_project, publish=False)
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(exercise_project / "study"))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        context = course_browser.new_context()
        try:
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/#{missing}")
            available = "Exercises" if missing == "study" else "Study"
            page.get_by_role("link", name="Open " + available, exact=True).click()
            expect(page.get_by_role("heading", level=1)).not_to_have_text(missing.capitalize())
            assert page.get_by_text("has not been prepared", exact=False).count() == 0
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


@pytest.mark.parametrize("exercise_only", [False, True])
def test_static_exercises_under_a_project_prefix(
    course_browser: Browser, exercise_project: Path, tmp_path: Path, exercise_only: bool
) -> None:
    if exercise_only:
        (exercise_project / "study/content.json").unlink()
    build(exercise_project, publish=False)
    host = tmp_path / "host"
    site = host / "course"
    site.mkdir(parents=True)
    for name, value in export_site(exercise_project, include_exercises=True).items():
        (site / name).write_bytes(value)
    context = course_browser.new_context(
        viewport={"width": 1440 if exercise_only else 390, "height": 900}
    )
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(host))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            page = context.new_page()
            requests = []
            errors = []
            page.on("request", lambda request: requests.append(request.url))
            page.on("pageerror", lambda error: errors.append(str(error)))
            base = f"http://127.0.0.1:{server.server_port}/course/"
            page.goto(base + "#exercises/sheet-1/sample-relaxation/candidate")
            page.get_by_label("Your answer", exact=True).fill("3")
            page.get_by_role("button", name="Check", exact=True).click()
            expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
            page.reload()
            expect(page.get_by_label("Your answer", exact=True)).to_have_value("3")
            assert errors == []
            assert all(url.startswith(base) for url in requests)
            assert not any("/_study/comments" in url for url in requests)
            if exercise_only:
                expect(page.get_by_role("link", name="Study", exact=True)).to_have_count(0)
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


@pytest.mark.parametrize("exercise_project", ["responses"], indirect=True)
def test_table_math_code_and_graph_work_survives_edits_reload_and_navigation(
    course_browser: Browser, exercise_url: str, exercise_project: Path
) -> None:
    # Each new response contract gets one behavioral journey, rather than a viewport matrix.
    context = course_browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        route = exercise_url + "#exercises/responses/response-controls/"
        page.goto(route + "table")
        total = page.get_by_label("Two pairs: Sum", exact=True)
        word = page.get_by_label("Two pairs: Name", exact=True)
        total.fill("3")
        expect(page.get_by_role("button", name="Check", exact=True)).to_be_disabled()
        word.fill(" FOUR ")
        page.get_by_role("button", name="Check", exact=True).click()
        expect(total).to_have_attribute("aria-invalid", "true")
        expect(word).not_to_have_attribute("aria-invalid", "true")
        total.fill("4")
        expect(total).not_to_have_attribute("aria-invalid", "true")
        page.get_by_role("button", name="Check", exact=True).click()
        expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
        page.reload()
        expect(word).to_have_value(" FOUR ")
        expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
        page.get_by_role("button", name="Continue", exact=True).click()
        math = page.get_by_label("Working", exact=True)
        math.fill("For n ≥ 1, pair i with n + 1 - i.\n" * 140)
        assert len(math.input_value()) > 4000
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(page.get_by_text("Checked correct", exact=True)).not_to_be_visible()
        page.get_by_role("button", name="Continue", exact=True).click()
        page.get_by_text("Starter", exact=True).click()
        page.get_by_role("button", name="Use", exact=True).click()
        code = page.get_by_label("Python draft", exact=True)
        expect(code).to_have_value("def add(a, b):\n    # Return the sum.\n    pass\n")
        code.fill("def add(a, b):\n    return a + b\n")
        expect(page.get_by_role("button", name="Use", exact=True)).to_be_disabled()
        expect(code).to_have_value("def add(a, b):\n    return a + b\n")
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        expect(page.get_by_label("Python draft", exact=True)).to_have_value(
            "def add(a, b):\n    return a + b\n"
        )
        page.get_by_role("button", name="Compare", exact=True).click()
        page.get_by_role("button", name="Continue", exact=True).click()
        for name in ("A", "C"):
            page.get_by_role("button", name=name, exact=True).click()
        page.get_by_role("button", name="Check", exact=True).click()
        expect(page.get_by_text("Check your reasoning", exact=True)).to_be_visible()
        page.get_by_role("button", name="Undo", exact=True).click()
        for name in ("B", "C"):
            page.get_by_role("button", name=name, exact=True).click()
        page.reload()
        expect(page.get_by_text("Path: A → B → C", exact=True)).to_be_visible()
        page.get_by_role("button", name="Check", exact=True).click()
        expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
        for step, labels in (("graph-nodes", ["A", "B", "C"]), ("graph-edges", ["A → B", "B → C"])):
            page.goto(route + step)
            for label in labels:
                page.get_by_role("checkbox", name=label, exact=True).check()
            page.get_by_role("button", name="Check", exact=True).click()
            expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
        assert errors == []
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        context.close()


def test_workspace_picker_is_single_keyboard_operable_and_pinned(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context(viewport={"width": 1440, "height": 600})
    try:
        page = context.new_page()
        page.goto(exercise_url)
        trigger = page.locator(".workspace-trigger")
        expect(trigger).to_have_count(1)
        assert page.locator("main .workspace-picker").count() == 0
        trigger.focus()
        trigger.press("Enter")
        expect(page.get_by_role("menuitemradio", name="Study", exact=True)).to_be_focused()
        page.keyboard.press("ArrowDown")
        expect(page.get_by_role("menuitemradio", name="Exercises", exact=True)).to_be_focused()
        page.keyboard.press("Escape")
        expect(trigger).to_be_focused()
        expect(page.get_by_role("menu", name="Choose workspace")).not_to_be_visible()
        trigger.click()
        page.locator("h1").click()
        expect(page.get_by_role("menu", name="Choose workspace")).not_to_be_visible()
        position = trigger.bounding_box()
        assert position and position["y"] > 480
        page.set_viewport_size({"width": 320, "height": 568})
        expand = page.get_by_role("button", name="Expand course outline", exact=True)
        if expand.is_visible():
            expand.click()
        trigger.click()
        page.keyboard.press("Escape")
        expect(trigger).to_be_focused()
        # Escape closes the menu first; a second press closes the mobile outline.
        page.keyboard.press("Escape")
        expect(page.get_by_role("button", name="Expand course outline", exact=True)).to_be_focused()
    finally:
        context.close()


@pytest.mark.parametrize("exercise_project", ["responses"], indirect=True)
def test_line_graph_tap_keyboard_coordinates_and_saved_verdict(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(exercise_url + "#exercises/responses/response-controls/plot")
        left, middle, right = [page.get_by_label(f"y at x = {x}", exact=True) for x in (-1, 0, 1)]
        left.fill("0")
        right.fill("2")
        graph = page.locator(".plot-response svg")
        box = graph.bounding_box()
        assert box
        # The actual chart maps x=0,y=1 to (324,158) in its 600x360 viewBox.
        graph.click(position={"x": box["width"] * 324 / 600, "y": box["height"] * 158 / 360})
        expect(middle).to_have_value("1")
        page.get_by_role("button", name="Check", exact=True).click()
        expect(page.get_by_text("Checked correct", exact=True)).to_be_visible()
        handle = page.get_by_role("slider", name="x = 0, y = 1", exact=True)
        handle.press("ArrowDown")
        expect(middle).to_have_value("0.5")
        expect(page.get_by_text("Checked correct", exact=True)).not_to_be_visible()
        page.get_by_role("button", name="Check", exact=True).click()
        expect(middle).to_have_attribute("aria-invalid", "true")
        middle.fill("1e309")
        expect(page.get_by_role("button", name="Check", exact=True)).to_be_disabled()
        middle.fill("1")
        page.reload()
        expect(middle).to_have_value("1")
        page.get_by_role("button", name="Check", exact=True).click()
        page.get_by_role("button", name="Finish", exact=True).click()
        expect(page.get_by_role("button", name="Reviewed", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        page.get_by_role("button", name="Clear", exact=True).click()
        expect(left).to_have_value("")
        expect(page.get_by_role("button", name="Check", exact=True)).to_be_disabled()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()


def test_section_references_are_compact_reachable_and_dismissible(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context(viewport={"width": 320, "height": 568})
    try:
        page = context.new_page()
        page.goto(exercise_url + "#weighted/content")
        note = page.locator(".read-section .citation").first
        summary = note.locator("summary")
        expect(note.locator(".citation-panel")).not_to_be_visible()
        assert summary.get_attribute("aria-label").startswith("Sources for ")
        summary.click()
        panel = note.locator(".citation-panel")
        expect(panel).to_be_visible()
        expect(panel).to_contain_text("Weighted paths")
        bounds = panel.bounding_box()
        assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 320
        summary.press("Escape")
        expect(panel).not_to_be_visible()
        expect(summary).to_be_focused()
        summary.click()
        page.locator("h1").click()
        expect(panel).not_to_be_visible()
        assert not page.get_by_role("link", name="Back to exercises", exact=True).count()
        assert not page.get_by_role("link", name="Back to question", exact=True).count()
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("exercise_project", ["responses"], indirect=True)
def test_step_arrows_keep_the_same_control_focus_and_alignment(
    course_browser: Browser, exercise_url: str, width: int
) -> None:
    context = course_browser.new_context(viewport={"width": width, "height": 844})
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/responses/response-controls/code")
        editor = page.get_by_label("Python draft", exact=True)
        editor.fill("def add(a, b):\n    return a + b\n")
        previous = page.get_by_role("button", name="Previous step", exact=True)
        following = page.get_by_role("button", name="Next step", exact=True)
        before = following.bounding_box()
        assert before
        # Real mouse navigation keeps the actual toolbar DOM and focus in place.
        following.evaluate('element => { element.dataset.originalControl = "true"; }')
        following.click()
        expect(
            page.get_by_role("heading", name="Build the directed path from A to C.", exact=True)
        ).to_be_visible()
        expect(following).to_have_attribute("data-original-control", "true")
        expect(following).to_be_focused()
        after = following.bounding_box()
        assert after and abs(after["y"] - before["y"]) <= 2
        previous.click()
        expect(editor).to_have_value("def add(a, b):\n    return a + b\n")
        expect(previous).to_be_focused()
        final = previous.bounding_box()
        assert final and abs(final["y"] - before["y"]) <= 2
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        context.close()


def test_ungraded_guidance_still_offers_prepared_explanation(
    course_browser: Browser, exercise_project: Path, exercise_url: str
) -> None:
    path = exercise_project / "study/exercises.json"
    payload = json.loads(path.read_bytes())
    step = payload["sets"][0]["exercises"][0]["steps"][0]
    step.pop("check")
    step["hints"] = []
    path.write_text(json.dumps(payload))
    build(exercise_project, publish=False)
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/candidate")
        page.get_by_role("button", name="Explain", exact=True).click()
        expect(
            page.locator("#content").get_by_text(step["explanation"], exact=True)
        ).to_be_visible()
        expect(page.get_by_role("button", name="Continue", exact=True)).to_be_enabled()
    finally:
        context.close()
