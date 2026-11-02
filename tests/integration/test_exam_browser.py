import json
import os
import re
from collections.abc import Iterator
from functools import partial
from threading import Thread

import pytest
from material_fixture import exam_document, exam_project, with_guided_paper
from playwright.sync_api import Browser, Page, expect

from tum_mcp.study_build import build
from tum_mcp.study_preview import Handler, PreviewServer

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


@pytest.fixture(scope="module")
def exam_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = exam_project(tmp_path_factory.mktemp("exam-browser"))
    (root / "app").mkdir()
    document = with_guided_paper(exam_document(root))
    # Exam replay accepts labelled steps without the exercise-only part-block contract.
    for step in document["sittings"][0]["variants"][0]["questions"][0]["guidance"]["steps"]:
        step["part"] = "(a)"
    # A meaning list may name its variable as bare LaTeX; the pilot's \lambda showed raw.
    for concept in document["concepts"]:
        for symbol in (concept.get("formula") or {}).get("symbols", []):
            symbol["symbol"] = symbol["symbol"].removeprefix("\\(").removesuffix("\\)")
    (root / "app/exam.json").write_text(json.dumps(document), encoding="utf-8")
    build(root, publish=False)
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(root / "app"))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)


def open_page(browser: Browser, url: str, width: int, errors: list[str]) -> Page:
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url + "#exam")
    page.get_by_role("heading", name="Exam", exact=True).wait_for()
    return page


def no_overflow(page: Page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


@pytest.mark.parametrize("width", [390, 1440])
def test_cheatsheet_scans_filters_flags_and_maps(
    course_browser: Browser, exam_url: str, width: int
) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, width, errors)
    expect(page.locator(".exam-profile")).to_contain_text("90 minutes")
    page.locator(".exam-card", has_text="Cheatsheet").click()
    page.get_by_role("heading", name="Cheatsheet", exact=True).wait_for()
    entries = page.locator(".exam-entry")
    expect(entries).to_have_count(6)
    expect(page.locator(".exam-sheet .unit-summary, .exam-toolbar")).to_have_count(0)
    page.locator("#concept-observer .exam-entry-row").click()
    # Every entry cites the same slides, so the page cites them once and no entry repeats it.
    expect(page.locator(".page-citation")).to_have_count(1)
    expect(page.locator(".exam-entry .citation")).to_have_count(0)
    expect(page.locator("#concept-observer .exam-cue.cue")).to_have_text("When you see")
    # An entry a pattern lists opens to that pattern's steps and leads on to practising them.
    steps = page.locator("#concept-observer .exam-entry-steps")
    expect(steps.locator(".exam-workflow > li").first).to_be_visible()
    expect(steps.get_by_role("link", name="Worked practice", exact=True)).to_have_attribute(
        "href", re.compile(r"#exam/patterns/.+/worked")
    )
    steps.get_by_role("link", name="Practise", exact=True).click()
    target = page.locator('[data-pattern-target="practise"]')
    expect(target.get_by_role("heading", name="Practise", exact=True)).to_be_visible()
    assert target.bounding_box()["y"] < 300
    if width < 800:
        page.get_by_role("button", name="Expand course outline", exact=True).click()
    page.locator('a[href="#exam/sheet"]').first.click()
    page.locator("#concept-observer .exam-entry-row").click()
    # An opened formula entry lists what each variable means in general.
    page.locator("#concept-cohesion .exam-entry-row").click()
    expect(page.locator(".symbols dd", has_text="method pairs sharing no field")).to_be_visible()
    # An entry taller than the screen ends with Collapse, which closes it and returns to its title.
    page.set_viewport_size({"width": width, "height": 320})
    page.locator("#concept-observer .exam-entry-row").click()
    page.locator("#concept-observer .exam-entry-row").click()
    collapse = page.locator("#concept-observer .exam-entry-collapse")
    expect(collapse).to_be_visible()
    collapse.click()
    expect(page.locator("#concept-observer > details")).not_to_have_attribute("open", "")
    expect(page.locator("#concept-observer > details > summary")).to_be_focused()
    page.set_viewport_size({"width": width, "height": 900})
    assert "\\" not in page.locator("#concept-cohesion .symbols").inner_text()
    expect(page.locator("#concept-cohesion .symbols dt .katex").first).to_be_visible()
    if width >= 720:
        node = page.locator('.exam-node[data-concept="loose-coupling"]')
        node.click()
        expect(page.locator(".exam-map-card")).to_contain_text("Depend on interfaces")
        expect(page.locator('.exam-node[data-concept="observer"]')).to_have_class(
            "exam-node core related"
        )
        node.focus()
        page.keyboard.press("ArrowRight")
        assert page.evaluate("document.activeElement.dataset.concept") != "loose-coupling"
        canvas = page.locator(".exam-map-scroll")
        canvas.scroll_into_view_if_needed()
        box = canvas.bounding_box()
        assert box is not None
        before = page.locator(".exam-map-svg").get_attribute("viewBox")
        page.mouse.move(box["x"] + 40, box["y"] + 40)
        page.mouse.down()
        page.mouse.move(box["x"] + 140, box["y"] + 90, steps=6)
        page.mouse.up()
        moved = page.locator(".exam-map-svg").get_attribute("viewBox")
        assert moved != before
        page.keyboard.down("Control")
        page.mouse.wheel(0, -300)
        page.keyboard.up("Control")
        zoomed = page.locator(".exam-map-svg").get_attribute("viewBox")
        assert zoomed and moved and float(zoomed.split()[2]) < float(moved.split()[2])
        # A node shows the same entry as the list, with its details, and stays open while the
        # student follows a connection to the next node.
        card = page.locator(".exam-map-card")
        page.locator('.exam-node[data-concept="observer"]').focus()
        page.keyboard.press("Enter")
        card.locator(".exam-entry-row").click()
        expect(card.locator(".exam-workflow > li").first).to_be_visible()
        expect(card.locator("[data-exam-item]")).to_have_count(0)
        assert page.evaluate(
            "(() => { const ids = [...document.querySelectorAll('[id]')].map(e => e.id);"
            " return ids.length === new Set(ids).size; })()"
        )
        expect(card.locator(".exam-map-connections")).to_have_count(0)
        page.locator('.exam-node[data-concept="loose-coupling"]').dispatch_event("click")
        expect(card).to_have_attribute("aria-label", "Loose coupling")
        page.locator('.exam-node[data-concept="observer"]').dispatch_event("click")
        expect(card.locator("details.exam-entry-details")).to_have_attribute("open", "")
        page.get_by_role("button", name="Full screen").click()
        expect(page.locator(".exam-map")).to_have_class(re.compile("expanded"))
        # Full screen keeps the entry beside the map, and Escape closes it before full screen.
        frame, pane = page.locator(".exam-map-scroll").bounding_box(), card.bounding_box()
        assert frame and pane and pane["x"] >= frame["x"] + frame["width"] - 1
        page.keyboard.press("Escape")
        expect(card).to_be_hidden()
        expect(page.locator(".exam-map")).to_have_class(re.compile("expanded"))
        page.get_by_role("button", name="Exit full screen").click()
        expect(page.locator(".exam-map")).not_to_have_class(re.compile("expanded"))
    else:
        expect(page.locator(".exam-map-scroll")).to_be_hidden()
        page.locator(".exam-map-topic summary", has_text="Structural patterns").click()
        page.locator(".exam-map-item", has_text="Decorator").click()
        expect(page.locator(".exam-map-card")).to_contain_text("Untested")
    no_overflow(page)
    assert errors == []


@pytest.mark.parametrize("width", [390, 1440])
def test_patterns_drills_and_worked_practice(
    course_browser: Browser, exam_url: str, width: int
) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, width, errors)
    page.goto(exam_url + "#exam/patterns")
    page.get_by_role("heading", name="Design an Observer", exact=True).wait_for()
    links = page.locator(".sidebar .unit-group", has_text="Exam patterns").locator(".unit-title")
    expect(links).to_have_text(
        ["Design an Observer", "Build a part-whole tree", "Swap an algorithm"]
    )
    expect(page.locator(".exam-instances tbody tr")).to_have_count(3)
    # The decision step lists its cases; the pitfall shows its wrong and right lines.
    expect(page.locator(".workflow-cases li")).to_have_count(2)
    # What a step or case applies opens under it; the answer template is no separate section.
    expect(page.get_by_role("heading", name="Answer template")).to_have_count(0)
    applies = page.locator(".exam-workflow .workflow-apply")
    expect(applies).to_have_count(3)
    expect(applies.locator(".apply-panel").first).to_be_hidden()
    for index in range(3):
        applies.nth(index).locator("summary").click()
    expect(applies.nth(0).locator(".apply-panel code.inline-code")).to_have_text("List<Observer>")
    expect(page.locator(".workflow-cases .apply-panel")).to_contain_text("o.update(state)")
    expect(applies.nth(2).locator(".apply-math .katex")).to_be_visible()
    # An applied formula's variables open their meaning in this pattern.
    applies.nth(2).locator(".apply-math [data-v]").first.click()
    expect(page.locator(".symbol-bubble")).to_contain_text("update calls one notify makes")
    page.keyboard.press("Escape")
    pitfall = page.locator(".pitfall")
    # The moment the mistake happens comes first, with its step.
    expect(pitfall.locator(":scope > :first-child")).to_have_text(
        "Step 3 Placing the notify call in the subject's state change."
    )
    expect(pitfall.locator(".pitfall-line")).to_have_text(
        ["Incorrect: notify() inside update()", "Correct: notify() after the state changes"]
    )
    # Practice without steps: every item, short or full, opens the same Solution panel.
    drill = page.locator(".exam-drill-item").first
    expect(drill.locator("code.inline-code")).to_have_text("List<Display>")
    expect(drill.get_by_label("Your answer")).to_have_count(0)
    expect(drill.get_by_role("button", name="Check")).to_have_count(0)
    expect(page.locator(".exam-drill-item summary", has_text="Compare")).to_have_count(0)
    drill.locator("summary", has_text="Solution").click()
    expect(drill.locator(".expected-value")).to_have_text("Subject")
    expect(drill.locator(".disclosure-panel")).to_contain_text("The subject owns registrations")
    full = page.locator(".exam-drill-item").nth(1)
    full.locator("summary", has_text="Solution").click()
    expect(full.locator(".disclosure-panel")).to_contain_text("update(Ship s)")
    # One example at a time; the which-case question uses the workflow's cases.
    practice = page.locator(".pattern-example:visible .exam-guided-step")
    expect(practice).to_have_count(3)
    which = practice.nth(1)
    expect(which.locator(".option")).to_have_count(2)
    which.get_by_label("Observers need different fields").check()
    which.get_by_role("button", name="Check").click()
    expect(which.locator(".feedback")).to_contain_text("No display needs another field.")
    practice.nth(2).locator("summary", has_text="Compare").click()
    expect(practice.nth(2)).to_contain_text("Loop over displays.")
    page.get_by_role("button", name="Example 2").click()
    expect(practice.nth(0)).to_contain_text("Which object changes?")
    page.get_by_role("button", name="Example 1").click()
    expect(which.locator(".feedback")).to_contain_text("No display needs another field.")
    no_overflow(page)
    assert errors == []


def test_sidebar_entries_can_be_marked_completed(course_browser: Browser, exam_url: str) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, 1440, errors)
    sheet = page.locator(".sidebar a.unit-link", has_text="Cheatsheet")
    sheet.click(button="right")
    page.get_by_role("menuitem", name="Mark as completed").click()
    expect(sheet.locator(".done-mark")).to_be_visible()
    expect(page.get_by_role("menu")).to_have_count(0)
    page.reload()
    expect(sheet.locator(".done-mark")).to_be_visible()
    sheet.focus()
    page.keyboard.press("Shift+F10")
    page.get_by_role("menuitem", name="Mark as not completed").press("Enter")
    expect(sheet.locator(".done-mark")).to_have_count(0)
    expect(sheet).to_be_focused()
    assert errors == []


@pytest.mark.parametrize("width", [390, 1440])
def test_guided_past_paper_uses_exercise_steps(
    course_browser: Browser, exam_url: str, width: int
) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, width, errors)
    page.goto(exam_url + "#exam/paper/ws23-a")
    page.locator(".exam-card", has_text="Guide").click()
    page.get_by_role("heading", name="Question 1", exact=True).first.wait_for()
    page.locator("summary", has_text="Guide").click()
    page.get_by_role("button", name="Compare").click()
    expect(page.locator(".exercise-feedback .expected-value")).to_have_text("station")
    page.locator("button.primary", has_text="Next step").click()
    page.get_by_role("heading", name="Write notifyObservers().").wait_for()
    editor = page.get_by_label("Your code (Java)")
    expect(editor).to_have_value("public void notifyObservers() {\n    // your code\n}")
    page.get_by_role("button", name="Compare").click()
    expect(page.locator(".model-code")).to_contain_text("o.update(temperature);")
    no_overflow(page)
    assert errors == []


@pytest.mark.parametrize("width", [390, 1440])
def test_practice_exam_shows_each_solution_on_demand(
    course_browser: Browser, exam_url: str, width: int
) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, width, errors)
    page.goto(exam_url + "#exam/mock/forecast-1")
    expect(page.locator(".exam-mode .notice")).to_contain_text("Not a past exam")
    expect(page.locator(".exam-question")).to_have_count(2)
    sequence = page.locator('.exam-question[data-question="f1-1"] svg.uml')
    expect(sequence.locator(".uml-participant")).to_have_count(3)
    expect(sequence.locator('[data-fragment="loop"]')).to_contain_text("for each member")
    expect(sequence.locator('[data-message="return"] .uml-line.dashed')).to_have_count(1)
    expect(sequence.locator(".uml-participant circle")).to_have_count(1)
    expect(page.get_by_role("heading", name="Question 1", exact=True)).to_have_count(0)
    expect(page.get_by_role("heading", name="Question 1 \u00b7 10 points")).to_have_count(1)
    first = page.locator('.exam-question[data-question="f1-1"]')
    expect(first.locator(".exam-solution")).not_to_have_attribute("open", "")
    first.locator(".exam-solution > summary").click()
    expect(first.locator(".exam-solution")).to_contain_text("Loop over members.")
    expect(first.locator(".exam-marking")).to_contain_text("Notification implemented (10)")
    expect(page.get_by_role("button", name="Start")).to_have_count(0)
    no_overflow(page)
    assert errors == []
