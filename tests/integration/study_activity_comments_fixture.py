"""Annotations follow original activity items through ordinary and pooled views."""

from pathlib import Path

from playwright.sync_api import Page
from study_comments_fixture import open_notes, select_passage


def activity_comment_checks(
    page: Page, project: Path, content: dict, view: str, pooled: bool
) -> None:
    from tum_mcp.study_comment_models import Delete
    from tum_mcp.study_comments import change_comment, read_comments

    owner = content["units"][1]
    if pooled:
        # A fresh browser pools every topic, in course order.
        page.goto(f"https://study.invalid/#revision?view={view}")
        first = content["units"][0]
        for _ in first["flashcards" if view == "flashcards" else "questions"]:
            page.get_by_role(
                "button",
                name="Next card (Right arrow)" if view == "flashcards" else "Next question",
                exact=True,
            ).click()
    else:
        page.goto(f"https://study.invalid/#{owner['key']}/{view}")
    selector = (
        ".card-front [data-comment-target]"
        if view == "flashcards"
        else ".option [data-comment-target]"
    )
    target = page.locator(selector).first
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    assert box
    # Native drag must not flip a card or choose a radio option.
    page.mouse.move(box["x"] + 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] - 2, box["y"] + box["height"] / 2, steps=8)
    page.mouse.up()
    if view == "flashcards":
        assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
    else:
        assert page.locator(".option input:checked").count() == 0
    # Deterministic quote length also covers short/long renderings across Chromium hosts.
    quote = select_passage(page, selector)
    page.get_by_role("button", name="Comment", exact=True).click()
    dialog = page.get_by_role("dialog", name="Comment", exact=True)
    dialog.get_by_label("Comment", exact=True).fill("Clarify this activity.")
    dialog.get_by_role("button", name="Save", exact=True).click()
    dialog.wait_for(state="hidden")
    popup = page.get_by_role("dialog", name="Comments", exact=True)
    popup.wait_for(state="visible")
    if view == "flashcards":
        page.keyboard.press("ArrowRight")
        assert (
            page.locator("[data-comment-target]").first.get_attribute("data-item-key")
            == owner["flashcards"][0]["key"]
        )
        assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
    saved = read_comments(project)
    assert len(saved["comments"]) == 1
    note = saved["comments"][0]
    assert note["anchor"]["unit_key"] == owner["key"]
    assert note["anchor"]["view"] == view and note["anchor"]["quote"] == quote
    assert (
        note["anchor"]["item_key"]
        == owner["flashcards" if view == "flashcards" else "questions"][0]["key"]
    )
    # The same note is visible in its original unit; passage returns to the correct item.
    page.get_by_role(
        "button",
        name="Next card (Right arrow)" if view == "flashcards" else "Next question",
        exact=True,
    ).click()
    assert page.locator(".comment-marker").count() == 0
    page.get_by_role(
        "button",
        name="Previous card (Left arrow)" if view == "flashcards" else "Previous question",
        exact=True,
    ).click()
    open_notes(page)
    page.get_by_role("button", name="Show passage", exact=True).click()
    page.get_by_role("button", name="Close comments", exact=True).click()
    if view == "flashcards":
        assert (
            page.locator(".card-front .recall-prompt").inner_text()
            == owner["flashcards"][0]["front"]
        )
        page.evaluate("getSelection().removeAllRanges()")
        page.locator(".flashcard").press("Space")
        quote = select_passage(page, ".card-back [data-comment-target]")
    else:
        question = owner["questions"][0]
        correct = next(
            option for option in question["options"] if option["key"] == question["correct"]
        )
        page.get_by_role("radio", name=correct["text"], exact=True).check()
        page.get_by_role("button", name="Check answer", exact=True).click()
        quote = select_passage(page, '[data-field="explanation"]')
    page.get_by_role("button", name="Comment", exact=True).click()
    dialog.get_by_label("Comment", exact=True).fill("Explain the answer.")
    dialog.get_by_role("button", name="Save", exact=True).click()
    dialog.wait_for(state="hidden")
    answer_note = read_comments(project)["comments"][-1]
    assert answer_note["anchor"]["field"] == ("back" if view == "flashcards" else "explanation")
    page.goto(f"https://study.invalid/#{owner['key']}/{view}")
    page.reload()
    open_notes(page)
    page.locator(f"#comment-{answer_note['id']}").get_by_role(
        "button", name="Show passage", exact=True
    ).click()
    if view == "flashcards":
        assert page.locator(".flashcard").get_attribute("data-revealed") == "true"
    else:
        page.get_by_text("Check an answer first.", exact=True).wait_for()
        row = page.locator(f"#comment-{answer_note['id']}")
        assert not row.locator(".comment-excerpt").is_visible()
        assert "note-quote-" not in row.get_by_role("button", name="Show passage").get_attribute(
            "aria-describedby"
        )
        assert page.locator(".option input:checked").count() == 0
        assert page.get_by_role("button", name="Check answer", exact=True).is_disabled()
    current = read_comments(project)
    for item in current["comments"]:
        current = change_comment(
            project,
            Delete(
                op="delete",
                id=item["id"],
                course_identity=current["course_identity"],
                expected_revision=current["revision"],
            ),
        )
