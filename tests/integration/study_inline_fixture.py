"""Inline notation and a mobile outline that never loses the student's place."""

import json
from pathlib import Path

from playwright.sync_api import Page, expect
from study_comments_fixture import open_notes, select_passage

# One typeset expression each, whether KaTeX or the MathML fallback rendered it.
EXPRESSIONS = ".inline-math"


def mobile_outline_checks(page: Page, content: dict) -> None:
    unit = content["units"][1]
    page.goto(f"https://study.invalid/#{unit['key']}/content")
    page.locator(".next-step").scroll_into_view_if_needed()
    before = page.evaluate("scrollY")
    assert before > 100
    menu = page.get_by_role("button", name="Expand course outline", exact=True).bounding_box()
    assert menu
    # Tap the sticky control in place; locator auto-scroll changes the reading position.
    page.mouse.click(menu["x"] + menu["width"] / 2, menu["y"] + menu["height"] / 2)
    overlay = page.get_by_role("dialog", name="Course outline", exact=True)
    box = overlay.bounding_box()
    assert box and box["y"] == 0 and box["height"] == page.viewport_size["height"]
    assert page.locator("main").get_attribute("inert") is not None
    assert overlay.get_by_role("link", name="Revision", exact=True).is_visible()
    overlay.locator(".sidebar-footer button").focus()
    page.keyboard.press("Tab")
    assert overlay.locator("a.course-title").evaluate("el => el === document.activeElement")
    page.keyboard.press("Escape")
    assert not overlay.count()
    assert abs(page.evaluate("scrollY") - before) <= 1
    assert page.locator("main").get_attribute("inert") is None
    assert page.get_by_role("button", name="Expand course outline", exact=True).evaluate(
        "el => el === document.activeElement"
    )


def inline_math_checks(page: Page, project: Path, content: dict) -> None:
    from tum_mcp.study_build import build

    source = project / "study/content.json"
    original = source.read_bytes()
    changed = json.loads(original)
    unit = changed["units"][0]
    phrase = r"Use \(v_i\) and \(n^2\) together. Cost $5. <img src=x onerror=bad()>"
    unit["blocks"][0]["paragraphs"] = [phrase]
    unit["flashcards"][0]["front"] = phrase
    unit["flashcards"][0]["back"] = r"For \(n=2\), \(n^2=4\)."
    unit["questions"][0]["prompt"] = r"Which value equals \(n^2\) for \(n=2\)?"
    unit["questions"][0]["options"][0]["text"] = r"The value \(4\)."
    unit["questions"][0]["explanation"] = r"Substitute \(n=2\) to get \(4\)."
    try:
        source.write_text(json.dumps(changed), encoding="utf-8")
        build(project, publish=False)
        page.goto(f"https://study.invalid/#{unit['key']}/content")
        page.reload()
        for view in ("content", "flashcards", "practice"):
            page.goto(f"https://study.invalid/#{unit['key']}/{view}")
            target = page.locator(
                ".reading-material p"
                if view == "content"
                else ".card-front .recall-prompt"
                if view == "flashcards"
                else ".practice-question legend"
            ).first
            expect(target.locator(EXPRESSIONS)).to_have_count(2)
            assert r"\(" not in target.text_content()
            assert not target.locator("img").count()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator(f".option {EXPRESSIONS}").count() == 1
        option = unit["questions"][0]["options"][0]
        page.locator(f"input[value='{option['key']}']").check()
        page.get_by_role("button", name="Check answer", exact=True).click()
        assert page.locator(f".feedback [data-field='explanation'] :is({EXPRESSIONS})").count() == 2
        page.goto(f"https://study.invalid/#{unit['key']}/flashcards")
        select_passage(page, ".card-front .recall-prompt")
        page.get_by_role("button", name="Comment", exact=True).click()
        editor = page.get_by_role("dialog", name="Comment", exact=True)
        editor.get_by_label("Comment", exact=True).fill("Inline notation context.")
        editor.get_by_role("button", name="Save", exact=True).click()
        editor.wait_for(state="hidden")
        page.reload()
        open_notes(page)
        page.get_by_role("button", name="Show passage", exact=True).click()
        assert not page.get_by_text("Passage unavailable", exact=True).count()
        page.get_by_role("button", name="Close comments", exact=True).click()
        page.evaluate("getSelection().removeAllRanges()")
        page.locator(".flashcard").click()
        assert page.locator(f".card-back :is({EXPRESSIONS})").count() == 2
    finally:
        from tum_mcp.study_comment_models import Delete
        from tum_mcp.study_comments import change_comment, read_comments

        notes = read_comments(project)
        for item in notes["comments"]:
            if item["text"] == "Inline notation context.":
                notes = change_comment(
                    project,
                    Delete(
                        op="delete",
                        id=item["id"],
                        course_identity=notes["course_identity"],
                        expected_revision=notes["revision"],
                    ),
                )
        source.write_bytes(original)
        build(project, publish=False)
        page.goto(f"https://study.invalid/#{content['units'][0]['key']}/content")
        page.reload()
