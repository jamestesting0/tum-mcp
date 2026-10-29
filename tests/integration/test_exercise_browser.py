"""A few real student journeys; logic edges are not multiplied by every viewport."""

import json
import os
import re
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser, Page, expect
from playwright.sync_api import TimeoutError as BrowserTimeout

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
        page.locator(".reading").get_by_text("Guidance", exact=True).click()
        # Students answer on paper: a compared step offers no answer box.
        expect(page.get_by_label("Your answer", exact=True)).to_have_count(0)
        page.get_by_role("button", name="Hint", exact=True).click()
        hint = page.locator("#content").get_by_text("A path cost includes all edges", exact=False)
        expect(hint).to_be_visible()
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        expect(hint).to_be_visible()
        page.get_by_role("button", name="Compare", exact=True).click()
        compared = page.locator(".exercise-feedback .feedback")
        expect(compared.locator(".expected-value")).to_have_text("3")
        expect(compared).to_contain_text("If yours differs: Include the cost of reaching A")
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
        page.locator(".reading").get_by_text("Solution", exact=True).click()
        expect(
            page.locator(".solution-answers").get_by_text("The candidate distance is", exact=False)
        ).to_be_visible()
        # Then no extra mode/form is required and the existing reading layout stays usable.
        assert errors == []
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        directory = Path(os.environ.get("TUM_MCP_EXERCISE_QA_PATH", str(tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(directory / f"{width}-guided-solution.png"))
    finally:
        context.close()


def test_repeat_clicks_and_reload_keep_one_comparison(
    course_browser: Browser, exercise_url: str
) -> None:
    # Given a numeric step that the student works out on paper.
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/candidate")
        prompt = page.get_by_role("heading", name="What is the cost through A?", exact=True)
        # When Compare is activated twice, it compares once and does not advance.
        page.get_by_role("button", name="Compare", exact=True).dblclick()
        expect(page.get_by_text("Compare with your work", exact=True)).to_be_visible()
        expect(prompt).to_be_visible()
        expect(page.get_by_text("Correct", exact=True)).not_to_be_visible()
        # Then the comparison survives a real reload.
        page.reload()
        expect(page.get_by_text("Compare with your work", exact=True)).to_be_visible()
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
        # When opening the solution directly and comparing the guided step.
        expect(page.get_by_role("button", name="Mark reviewed", exact=True)).to_have_count(0)
        page.locator(".reading").get_by_text("Solution", exact=True).click()
        expect(
            page.locator(".solution-answers").get_by_text(
                "Take the first unsettled vertex", exact=False
            )
        ).to_be_visible()
        page.locator(".reading").get_by_text("Guidance", exact=True).click()
        page.get_by_role("button", name="Compare", exact=True).click()
        # Then comparison is available with no typed response or automatic correctness claim.
        expect(page.get_by_label("Your answer", exact=True)).not_to_be_visible()
        expect(page.get_by_text("The minimum-choice rule says", exact=False)).to_be_visible()
        expect(page.get_by_text("Correct", exact=True)).not_to_be_visible()
        # Finishing marks the exercise completed in the outline.
        page.get_by_role("button", name="Finish", exact=True).click()
        page.get_by_role("button", name="Expand course outline", exact=True).click()
        outline_entry = page.locator(".sidebar a.unit-link", has_text="Exercise 2")
        expect(outline_entry.locator(".done-mark")).to_be_visible()
        expect(outline_entry).not_to_contain_text("Reviewed")
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
        page.get_by_role("button", name="Check answer", exact=True).click()
        verdict = page.locator(".exercise-feedback > .feedback")
        expect(verdict).to_contain_text("Include the cost of reaching the neighbor")
        explanations = page.locator(".option-explanations")
        expect(explanations).not_to_have_attribute("open", "")
        explanations.locator("summary").click()
        expect(explanations.locator("li.right")).to_contain_text("Keep 8")
        page.get_by_label("Keep 8", exact=True).check()
        expect(page.get_by_text("Not quite", exact=True)).not_to_be_visible()
        page.get_by_role("button", name="Check answer", exact=True).click()
        page.get_by_role("button", name="Finish", exact=True).click()
        path = exercise_project / "study/exercises.json"
        payload = json.loads(path.read_bytes())
        payload["sets"][0]["exercises"][0]["steps"][0]["prompt"] += " Explain the path cost."
        path.write_text(json.dumps(payload))
        build(exercise_project, publish=False)
        page.reload()
        # A changed exercise starts fresh, while the older record stays in storage.
        expect(page.get_by_label("Keep 8", exact=True)).not_to_be_checked()
        expect(page.get_by_text("Exercise updated · previous responses", exact=True)).to_have_count(
            0
        )
        records = """() => Object.keys(localStorage)
            .filter(key => key.startsWith('course-exercises:'))
            .filter(key => JSON.parse(localStorage.getItem(key))?.steps?.['transfer-choice']?.draft)
            .length"""
        assert page.evaluate(records) == 1
        page.get_by_label("Replace with 6", exact=True).check()
        page.reload()
        assert page.evaluate(records) == 2
        page.evaluate("localStorage.setItem('study-space:other-course:progress:v1', 'keep')")
        page.locator(".course-title").click()
        page.get_by_role("button", name="Reset progress", exact=True).click()
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
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(page.get_by_text("Compare with your work", exact=True)).to_be_visible()
        expect(page.get_by_text("Progress cannot be saved", exact=False)).to_be_visible()
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        expect(page.get_by_text("Compare with your work", exact=True)).to_be_visible()
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
            try:
                page.get_by_role("button", name="Compare", exact=True).wait_for()
            except BrowserTimeout:
                pytest.fail(
                    f"Static exercise did not become usable: url={page.url!r}, "
                    f"page_errors={errors!r}, body={page.locator('body').inner_text()[:2000]!r}",
                    pytrace=False,
                )
            page.get_by_role("button", name="Compare", exact=True).click()
            expect(page.get_by_text("Compare with your work", exact=True)).to_be_visible()
            page.reload()
            expect(page.get_by_text("Compare with your work", exact=True)).to_be_visible()
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
        # The table is filled in on paper: answer cells stay empty, nothing is typed.
        expect(page.locator(".answer-table td.blank-cell")).to_have_count(2)
        expect(page.locator(".answer-table input")).to_have_count(0)
        page.get_by_role("button", name="Compare", exact=True).click()
        expected = page.locator(".expected-answer table")
        expect(expected.locator("tbody tr").first).to_contain_text("4")
        page.reload()
        expect(expected).to_be_visible()
        page.get_by_role("button", name="Continue", exact=True).click()
        expect(page.locator(".exercise-response textarea")).to_have_count(0)
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(page.get_by_text("Correct", exact=True)).not_to_be_visible()
        page.get_by_role("button", name="Continue", exact=True).click()
        code = page.get_by_label("Your code (Python)", exact=True)
        expect(code).to_have_value("def add(a, b):\n    # Return the sum.\n    pass\n")
        code.fill("def add(a, b):\n    return a + b\n")
        expect(code).to_have_value("def add(a, b):\n    return a + b\n")
        switch_workspace(page, "Study")
        switch_workspace(page, "Exercises")
        expect(page.get_by_label("Your code (Python)", exact=True)).to_have_value(
            "def add(a, b):\n    return a + b\n"
        )
        page.get_by_role("button", name="Compare", exact=True).click()
        page.get_by_role("button", name="Continue", exact=True).click()
        for name in ("A", "C"):
            page.get_by_role("button", name=name, exact=True).click()
        page.get_by_role("button", name="Undo", exact=True).click()
        for name in ("B", "C"):
            page.get_by_role("button", name=name, exact=True).click()
        page.reload()
        expect(page.get_by_text("Path: A → B → C", exact=True)).to_be_visible()
        page.get_by_role("button", name="Compare", exact=True).click()
        # The answer is drawn on the graph, with the same path in words as its caption.
        compared = page.locator(".feedback.compare")
        expect(compared.locator(".diagram-state")).to_contain_text("Path: A → B → C")
        expect(compared.locator(".graph g.active")).to_have_count(3)
        expect(compared.locator(".graph line.active")).to_have_count(2)
        for step, labels, shown in (
            ("graph-nodes", ["A", "B", "C"], "Nodes: A, B, C"),
            ("graph-edges", ["A → B", "B → C"], "Edges: A–B, B–C"),
        ):
            page.goto(route + step)
            for label in labels:
                page.get_by_role("checkbox", name=label, exact=True).check()
            page.get_by_role("button", name="Compare", exact=True).click()
            expect(page.locator(".feedback.compare .diagram-state")).to_contain_text(shown)
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
def test_line_graph_tap_keyboard_coordinates_and_saved_comparison(
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
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(page.locator(".expected-answer tbody tr")).to_have_count(3)
        handle = page.get_by_role("slider", name="x = 0, y = 1", exact=True)
        handle.press("ArrowDown")
        expect(middle).to_have_value("0.5")
        expect(page.locator(".expected-answer")).to_have_count(0)
        middle.fill("1")
        page.reload()
        expect(middle).to_have_value("1")
        page.get_by_role("button", name="Compare", exact=True).click()
        page.get_by_role("button", name="Finish", exact=True).click()
        assert page.evaluate("""() => Object.entries(localStorage)
            .some(([key, value]) => key.endsWith(':completed:v1')
                && JSON.parse(value)['#exercises/responses/response-controls'] === true)""")
        page.get_by_role("button", name="Clear", exact=True).click()
        expect(left).to_have_value("")
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
        # Every section cites the same source, so the page cites it once beside its eyebrow.
        expect(page.locator(".read-section .citation:visible")).to_have_count(0)
        note = page.locator(".page-citation")
        summary = note.locator("summary")
        expect(note.locator(".citation-panel")).not_to_be_visible()
        assert summary.get_attribute("aria-label") == "Sources for this page"
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
        # Any click outside the note closes it; the open panel itself covers the title.
        page.mouse.click(160, 548)
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
        editor = page.get_by_label("Your code (Python)", exact=True)
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


def test_compare_is_the_one_place_a_step_reveals_its_reasoning(
    course_browser: Browser, exercise_project: Path, exercise_url: str
) -> None:
    path = exercise_project / "study/exercises.json"
    payload = json.loads(path.read_bytes())
    steps = payload["sets"][0]["exercises"][0]["steps"]
    ungraded = steps[0]
    ungraded.pop("check")
    ungraded["hints"] = ["Add the edge to the distance of A."]
    path.write_text(json.dumps(payload))
    build(exercise_project, publish=False)
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/candidate")
        explanation = page.locator("#content").get_by_text(ungraded["explanation"], exact=True)
        # Hints run out without turning into a second way to reveal the answer.
        page.get_by_role("button", name="Hint", exact=True).click()
        expect(page.get_by_role("button", name="Next hint", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="Show explanation", exact=True)).to_have_count(0)
        expect(explanation).to_have_count(0)
        # A step without a check is compared too, and shows its reasoning once.
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(explanation).to_have_count(1)
        expect(page.get_by_role("button", name="Continue", exact=True)).to_be_enabled()
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_study_passages_terms_and_answers_open_in_place_without_losing_work(
    course_browser: Browser, exercise_project: Path, exercise_url: str, width: int
) -> None:
    # Given a Study definition the exercise names, a marked term in a step and two part answers.
    content_path = exercise_project / "study/content.json"
    content = json.loads(content_path.read_bytes())
    weighted = next(unit for unit in content["units"] if unit["key"] == "weighted")
    weighted["blocks"].insert(
        0,
        {
            "kind": "definition",
            "key": "relaxation",
            "sources": ["weighted"],
            "term": "Relaxation",
            "statement": "Replacing a distance estimate by a cheaper one found through a neighbor.",
        },
    )
    content_path.write_text(json.dumps(content))
    path = exercise_project / "study/exercises.json"
    payload = json.loads(path.read_bytes())
    exercise = payload["sets"][0]["exercises"][0]
    exercise["prerequisites"][0]["block"] = "relaxation"
    exercise["steps"][1]["prompt"] = "Why does {{relaxation}} replace d(B)?"
    exercise["parts"] = ["(a) Compute the cost through A.", "(b) Decide whether to replace d(B)."]
    answer = exercise["solution"]["answers"][0]
    exercise["solution"]["answers"] = [answer | {"label": "(a)"}, answer | {"label": "(b)"}]
    path.write_text(json.dumps(payload))
    build(exercise_project, publish=False)
    context = course_browser.new_context(viewport={"width": width, "height": 900})
    try:
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(exercise_url + "#exercises/sheet-1/sample-relaxation/reason")
        prompt = page.get_by_role("heading", name="Why does Relaxation replace d(B)?")
        expect(prompt).to_be_visible()
        scroll = "(document.scrollingElement.scrollTop || document.querySelector('main').scrollTop)"
        # When the student opens the term, then the Study passage, then closes it.
        page.get_by_role("button", name="relaxation", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="cheaper one")).to_be_visible()
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Review Relaxation", exact=True).click()
        panel = page.get_by_role("dialog", name="Relaxation")
        expect(panel).to_contain_text("through a neighbor")
        # Measured with the panel open: a click first scrolls its target into view.
        before = page.evaluate(scroll)
        expect(panel.get_by_role("link", name="Open in Study")).to_have_attribute(
            "href", "#weighted/content/relaxation"
        )
        panel.get_by_role("button", name="Close", exact=True).click()
        # Then the same step, focus point and scroll position remain, and nothing navigated.
        expect(panel).to_have_count(0)
        expect(page.get_by_role("button", name="Review Relaxation")).to_be_focused()
        assert page.url.endswith("#exercises/sheet-1/sample-relaxation/reason")
        assert abs(page.evaluate(scroll) - before) <= 2
        # And the solution answers each original part under its own label.
        page.locator(".reading").get_by_text("Solution", exact=True).click()
        labels = page.locator(".solution-label")
        expect(labels).to_have_text(["(a)", "(b)"])
        assert errors == []
    finally:
        context.close()


def test_local_preview_opens_only_inventory_files(
    exercise_project: Path, exercise_url: str
) -> None:
    from http.client import HTTPConnection

    from tum_mcp.study_store import load_state

    stored = next(item.path for item in load_state(exercise_project).resources if item.path)
    host = exercise_url.removeprefix("http://").rstrip("/")

    def fetch(path: str) -> int:
        connection = HTTPConnection(host, timeout=5)
        try:
            connection.request("GET", "/" + path, headers={"Host": host})
            return connection.getresponse().status
        finally:
            connection.close()

    # A cited course file opens in the local preview; nothing else under materials does.
    assert fetch(stored) == 200
    assert fetch("materials/../.tum-mcp/state.json") == 404
    assert fetch(stored.rsplit("/", 1)[0] + "/unlisted.md") == 404


def test_outline_names_only_categories_that_add_information(
    course_browser: Browser, exercise_project: Path, exercise_url: str
) -> None:
    path = exercise_project / "study/exercises.json"
    payload = json.loads(path.read_bytes())
    first = payload["sets"][0]
    first.update(category="Exercise 1", title="Exercise 1: Shortest paths")
    groups = [first]
    for number, (category, title) in enumerate(
        [("Exercise 2", "Exercise 2: Search"), ("Tutorials", "Sheet 3"), ("Tutorials", "Sheet 4")],
        start=2,
    ):
        group = json.loads(json.dumps(first))
        group.update(key=f"sheet-{number}", category=category, title=title)
        for exercise in group["exercises"]:
            exercise["key"] = f"{exercise['key']}-{number}"
        groups.append(group)
    payload["sets"] = groups
    path.write_text(json.dumps(payload))
    build(exercise_project, publish=False)
    context = course_browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises")
        listing = page.locator(".exercise-list")
        # "Exercise 2" only repeats its set's title, so a thin rule marks the new group.
        expect(listing.get_by_text("Exercise 2", exact=True)).to_have_count(0)
        expect(listing.get_by_role("heading", name="Tutorials", exact=True)).to_have_count(1)
        sheets = listing.locator(".exercise-sheet")
        expect(sheets).to_have_count(4)
        borders = sheets.evaluate_all("els => els.map(el => getComputedStyle(el).borderTopStyle)")
        # Groups are separated by spacing alone; no rule lines between sheets.
        assert borders == ["none", "none", "none", "none"]
    finally:
        context.close()


def test_distilled_code_practice_writes_code_and_checks_literal_code(
    course_browser: Browser, exercise_url: str, exercise_project: Path
) -> None:
    path = exercise_project / "study/exercises.json"
    payload = json.loads(path.read_bytes())
    original = payload["sets"][0]["exercises"][0]
    source = original["sources"][0]["key"]
    starter = "List<Integer> sorted(List<Integer> items) {\n    // your code\n}"
    model = (
        "List<Integer> sorted(List<Integer> items) {\n"
        "    List<Integer> copy = new ArrayList<>(items);\n"
        "    copy.sort(null);\n    return copy;\n}"
    )
    payload["sets"][0]["exercises"].append(
        {
            "key": "copy-drill",
            "label": "Drill",
            "title": "Sort a copy",
            "kind": "distilled",
            "distilled_from": [original["key"]],
            "sources": original["sources"],
            "statement": [
                {
                    "kind": "code",
                    "title": "Starting point",
                    "sources": [source],
                    "language": "java",
                    "code": "List<Integer> sorted(List<Integer> items) {\n  // sort a copy\n}",
                    "explanation": "The caller keeps its list unchanged.",
                    "line_numbers": True,
                }
            ],
            "objectives": ["Sort without changing the input."],
            "steps": [
                {
                    "key": "write",
                    "purpose": "Write the method",
                    "prompt": "Write sorted().",
                    "explanation": "Copy, sort the copy, return it.",
                    "check": {
                        "kind": "self_check",
                        "format": "code",
                        "language": "java",
                        "starter_code": starter,
                        "model_answer": model,
                        "rubric": ["Sorts a copy", "Leaves the caller's list unchanged"],
                    },
                },
                {
                    "key": "finish",
                    "purpose": "Return it",
                    "prompt": "Write the final statement.",
                    "explanation": "Return the sorted copy.",
                    "check": {
                        "kind": "text",
                        "format": "code",
                        "language": "java",
                        "answer": "return copy;",
                        "feedback": "Return the copy, not the input.",
                    },
                },
            ],
            "solution": original["solution"],
        }
    )
    path.write_text(json.dumps(payload))
    build(exercise_project, publish=False)
    context = course_browser.new_context()
    try:
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(exercise_url + "#exercises/sheet-1/copy-drill")
        expect(page.locator(".practice-for")).to_contain_text(original["title"])
        expect(page.locator(".code-region .code-line")).to_have_count(3)
        page.locator(".reading").get_by_text("Guidance", exact=True).click()
        editor = page.get_by_label("Your code (Java)", exact=True)
        expect(editor).to_have_value(starter)
        editor.evaluate(
            "e => e.setSelectionRange(e.value.indexOf('{') + 1, e.value.indexOf('{') + 1)"
        )
        editor.press("Enter")
        editor.press_sequentially("return copy;")
        assert editor.input_value().startswith(
            "List<Integer> sorted(List<Integer> items) {\n    return copy;"
        )
        editor.press("Tab")
        assert "return copy;    " in editor.input_value()
        editor.press("Escape")
        editor.press("Tab")
        assert page.evaluate("document.activeElement.tagName") != "TEXTAREA"
        page.reload()
        expect(editor).to_have_value(re.compile(r"\{\n    return copy;"))
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(page.locator(".model-code")).to_contain_text("copy.sort(null);")
        page.get_by_role("button", name="Continue", exact=True).click()
        expect(page.get_by_label("java answer", exact=True)).to_have_count(0)
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(page.get_by_text("Return the copy, not the input.", exact=False)).to_be_visible()
        expect(page.locator(".model-code")).to_contain_text("return copy;")
        page.locator(".practice-for a").click()
        expect(page.get_by_role("heading", name=original["title"], exact=True)).to_be_visible()
        assert errors == []
    finally:
        context.close()


@pytest.mark.parametrize("exercise_project", ["responses"], indirect=True)
def test_project_files_open_referenced_lines_and_keep_edits(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(exercise_url + "#exercises/responses/project-files/read")
        project = page.locator(".project")
        expect(project.locator(".project-tab-item.active")).to_have_text("Counter.java")
        expect(project.locator(".tok-keyword").first).to_be_visible()
        expect(page.locator(".page-citation")).to_have_count(1)
        expect(page.locator("main .source-note:visible")).to_have_count(1)
        project.get_by_role("button", name="Hide files").click()
        expect(project.locator(".project-tree")).to_be_hidden()
        project.get_by_role("button", name="Show files").click()
        expect(project.locator(".project-tree")).to_be_visible()
        reference = page.locator(".code-ref")
        expect(reference.locator(".code-ref-path")).to_have_text("src/Main.java")
        expect(reference.locator(".code-line")).to_have_count(3)
        reference.get_by_role("button", name="Open in files").click()
        expect(project.locator(".project-tab-item.active")).to_have_text("Main.java")
        expect(project.locator(".code-line.marked")).to_have_count(3)
        page.goto(exercise_url + "#exercises/responses/project-files/write")
        # The step already shows Counter.java's lines, so it opens from that excerpt only.
        expect(page.get_by_role("button", name="Open Counter.java")).to_have_count(0)
        page.locator(".code-ref").get_by_role("button", name="Open in files").click()
        editor = page.get_by_label("Edit src/Counter.java", exact=True)
        expect(editor).to_have_value(re.compile(r"// TODO: add one"))
        editor.evaluate(
            "e => e.setSelectionRange(e.value.indexOf('// TODO'), e.value.indexOf('// TODO') + 15)"
        )
        editor.press_sequentially("count++;")
        page.reload()
        page.locator(".code-ref").get_by_role("button", name="Open in files").click()
        expect(editor).to_have_value(re.compile(r"count\+\+;"))
        expect(project.locator(".project-tab.changed")).to_have_count(1)
        page.get_by_role("button", name="Compare", exact=True).click()
        expect(page.locator(".model-code")).to_contain_text("count++;")
        project.get_by_role("button", name="Reset file", exact=True).click()
        expect(editor).to_have_value(re.compile(r"// TODO: add one"))
        assert errors == []
    finally:
        context.close()


def test_demo_walkthrough_and_state_diagram(course_browser: Browser, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from tum_mcp.cli import app

    root = tmp_path / "demo"
    result = CliRunner().invoke(app, ["study", "demo", str(root)])
    assert result.exit_code == 0, result.output
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(root / "app"))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        context = course_browser.new_context()
        try:
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/#components/content")
            walk = page.locator(".code-walkthrough")
            expect(walk.locator(".code-walk-note")).to_contain_text("takes one input")
            expect(walk.locator(".code-line.marked")).to_have_count(1)
            walk.get_by_role("button", name="Next stop").click()
            expect(walk.locator(".code-walk-note")).to_contain_text("twice")
            expect(walk.get_by_role("button", name="Next stop")).to_be_disabled()
            state = page.locator('.uml-region[aria-label="UML state diagram"]')
            expect(state.locator(".uml-state")).to_have_count(5)
            expect(state.locator(".uml-transition")).to_have_count(6)
            expect(page.locator(".project")).to_have_count(1)
            tree = page.locator(".tree")
            expect(tree.locator(".tree-row")).to_have_count(5)
            expect(tree.locator(".tree-note")).to_have_count(3)
            assert errors == []
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=3)


@pytest.mark.parametrize("exercise_project", ["responses"], indirect=True)
def test_steps_never_leave_empty_space_to_scroll_into(
    course_browser: Browser, exercise_url: str
) -> None:
    context = course_browser.new_context(viewport={"width": 1280, "height": 745})
    try:
        page = context.new_page()
        page.goto(exercise_url + "#exercises/responses/response-controls/choice")
        page.get_by_role("button", name="Check answer").wait_for()
        # Hidden labels far down the reading pane must not make the whole page scroll.
        assert page.evaluate("document.scrollingElement.scrollHeight <= innerHeight")
        page.goto(exercise_url + "#exercises/responses/response-controls/number")
        workspace, padding = page.locator(".exercise-workspace"), "0px"
        # Arrow on until a shorter step needs padding to hold the arrows in place.
        for _ in range(9):
            page.get_by_role("button", name="Next step", exact=True).click()
            padding = workspace.evaluate("e => e.style.paddingBottom")
            if padding not in ("", "0px"):
                break
        assert padding not in ("", "0px")
        # That padding goes once the student scrolls back up.
        page.locator("main").evaluate("m => m.scrollTo({ top: 0, behavior: 'instant' })")
        expect(workspace).to_have_css("padding-bottom", "0px")
    finally:
        context.close()
