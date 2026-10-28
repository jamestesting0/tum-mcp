import json
import os
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
    page.get_by_role("heading", name="Exam Prep", exact=True).wait_for()
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
    page.get_by_role("searchbox", name="Search the cheatsheet").fill("interchangeable")
    expect(page.locator(".exam-entry:visible")).to_have_count(1)
    expect(page.locator(".exam-filter-status")).to_have_text("1 of 6 entries shown")
    page.get_by_role("searchbox", name="Search the cheatsheet").fill("")
    page.get_by_role("button", name="Mark for review: Observer").click()
    page.get_by_role("button", name="Review only").click()
    expect(page.locator(".exam-entry:visible")).to_have_count(1)
    page.reload()
    page.get_by_role("button", name="Review only").click()
    expect(page.locator(".exam-entry:visible")).to_have_count(1)
    page.get_by_role("button", name="Review only").click()
    page.get_by_role("button", name="Expand all").click()
    expect(page.locator(".exam-entry-details[open]")).to_have_count(6)
    expect(page.locator("#concept-observer")).to_contain_text("When you see:")
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
    else:
        expect(page.locator(".exam-map-scroll")).to_be_hidden()
        page.locator(".exam-map-topic summary", has_text="Structural patterns").click()
        page.locator(".exam-map-item", has_text="Decorator").click()
        expect(page.locator(".exam-map-card")).to_contain_text("Not yet tested")
    no_overflow(page)
    assert errors == []


@pytest.mark.parametrize("width", [390, 1440])
def test_patterns_drills_and_recognition(
    course_browser: Browser, exam_url: str, width: int
) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, width, errors)
    page.goto(exam_url + "#exam/patterns")
    links = page.locator(".exam-pattern-list .unit-title")
    expect(links).to_have_text(
        ["Design an Observer", "Build a part-whole tree", "Swap an algorithm"]
    )
    recognition = page.locator(".exam-recognition")
    recognition.get_by_label("Design an Observer").check()
    expect(recognition.locator(".feedback")).to_contain_text("Correct")
    page.goto(exam_url + "#exam/patterns/observer-design")
    page.get_by_role("heading", name="Design an Observer", exact=True).wait_for()
    expect(page.locator(".exam-instances tbody tr")).to_have_count(3)
    drill = page.locator(".exam-drill-item")
    drill.get_by_label("Your answer").fill("Subject")
    drill.get_by_role("button", name="Check answer").click()
    expect(drill.locator(".feedback")).to_contain_text("The subject owns registrations")
    no_overflow(page)
    assert errors == []


@pytest.mark.parametrize("width", [390, 1440])
def test_guided_past_paper_uses_exercise_steps(
    course_browser: Browser, exam_url: str, width: int
) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, width, errors)
    page.goto(exam_url + "#exam/paper/ws23-a")
    page.locator(".exam-card", has_text="Guided").click()
    page.get_by_role("heading", name="Question 1", exact=True).first.wait_for()
    page.locator("summary", has_text="Guidance").click()
    page.get_by_label("Your answer").fill("Weather station")
    page.get_by_role("button", name="Check answer").click()
    expect(page.locator(".exercise-feedback")).to_contain_text("Correct")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("heading", name="Order the lines of notify().").wait_for()
    order = page.locator(".order-list")

    def arrange() -> list[str]:
        return order.locator(".order-item code").all_inner_texts()

    for line in ("for (Observer o : observers) {", "  o.update(temperature);", "}"):
        while arrange().index(line) > [
            "for (Observer o : observers) {",
            "  o.update(temperature);",
            "}",
        ].index(line):
            page.get_by_role("button", name=f'Move "{line.strip()}" up').click()
    page.get_by_role("checkbox").nth(arrange().index("observers.clear();")).check()
    page.get_by_role("button", name="Check answer").click()
    expect(page.locator(".exercise-feedback")).to_contain_text("Correct")
    no_overflow(page)
    assert errors == []


@pytest.mark.parametrize("width", [390, 1440])
def test_practice_exam_mode_scores_and_retakes(
    course_browser: Browser, exam_url: str, width: int
) -> None:
    errors: list[str] = []
    page = open_page(course_browser, exam_url, width, errors)
    page.goto(exam_url + "#exam/mock/forecast-1")
    expect(page.locator(".exam-mode .notice")).to_contain_text("not a past or leaked exam")
    page.get_by_label("Use a 90-minute timer").uncheck()
    page.get_by_role("button", name="Start").click()
    page.locator('.exam-question[data-question="f1-2"]').get_by_label("Wraps at runtime").check()
    page.get_by_role("button", name="Finish and see results").click()
    page.get_by_role("dialog").get_by_role("button", name="Finish").click()
    expect(page.locator(".exam-score")).to_have_text("4 of 18 points")
    manual = page.get_by_label("Same interface (4)")
    manual.check()
    expect(page.locator(".exam-score")).to_have_text("8 of 18 points")
    assert page.evaluate("document.activeElement.type") == "checkbox"
    expect(page.locator(".exam-summary")).to_contain_text("Design an Observer")
    page.reload()
    expect(page.locator(".exam-score")).to_have_text("8 of 18 points")
    page.get_by_role("button", name="Retake").click()
    page.get_by_role("dialog").get_by_role("button", name="Retake").click()
    page.get_by_role("button", name="Start").wait_for()
    no_overflow(page)
    assert errors == []
