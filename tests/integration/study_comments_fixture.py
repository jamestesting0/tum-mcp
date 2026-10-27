"""Passage-feedback flows in an owned browser and a synthetic local project."""

import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page
from study_popover_fixture import popover_checks


def select_passage(page: Page, selector: str = ".reading-material p") -> str:
    return page.locator(selector).first.evaluate("""element => {
      const text = element.firstChild, range = document.createRange();
      range.setStart(text, 0); range.setEnd(text, Math.min(text.length, 64));
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
      return range.toString().replace(/\\s+/g, ' ').trim();
    }""")


def open_notes(page: Page) -> None:
    if not page.locator(".comment-popover").is_visible():
        page.locator(".comment-marker").first.click()
    page.get_by_role("dialog", name="Comments", exact=True).wait_for(state="visible")


def comment_checks(page: Page, project: Path) -> None:
    from tum_mcp.study_build import build
    from tum_mcp.study_comment_models import Create, Delete, Edit, SetStatus
    from tum_mcp.study_comments import change_comment, read_comments

    quote = select_passage(page)
    page.get_by_role("button", name="Comment", exact=True).click()
    dialog = page.get_by_role("dialog", name="Comment", exact=True)
    assert dialog.locator("blockquote").inner_text() == quote
    text = "Explain the assumption. <script>window.notExecuted = true</script>"
    dialog.get_by_label("Comment", exact=True).fill(text)
    dialog.get_by_role("button", name="Save", exact=True).click()
    dialog.wait_for(state="hidden")
    saved = read_comments(project)
    assert len(saved["comments"]) == 1
    note = saved["comments"][0]
    assert note["anchor"]["quote"] == quote and note["text"] == text
    assert page.locator(".comment-note .comment-text").inner_text() == text
    assert page.locator(".comment-controls button, .comment-more > summary").evaluate_all(
        """elements => elements.every(element => {
          const r = element.getBoundingClientRect(); return r.width >= 44 && r.height >= 44;
        })"""
    )
    assert not page.locator(".comment-note .comment-excerpt").is_visible()
    assert not page.evaluate("Boolean(window.notExecuted)")
    popover_checks(page)
    page.reload()
    open_notes(page)
    page.get_by_role("button", name="Show passage", exact=True).click()
    assert page.get_by_role("dialog", name="Comments", exact=True).is_visible()
    # Keyboard selection can open and cancel a draft without adding another note.
    select_passage(page)
    page.keyboard.press("Control+Alt+m")
    dialog.wait_for(state="visible")
    dialog.get_by_role("button", name="Cancel", exact=True).click()
    assert len(read_comments(project)["comments"]) == 1
    open_notes(page)
    page.get_by_label("More actions", exact=True).click()
    page.get_by_role("button", name="Edit", exact=True).click()
    dialog.get_by_label("Comment", exact=True).fill("My preserved draft")
    current = read_comments(project)
    concurrent = Edit(
        op="edit",
        id=note["id"],
        course_identity=current["course_identity"],
        expected_revision=current["revision"],
        text="Concurrent new feedback",
    )
    change_comment(project, concurrent)
    dialog.get_by_text("Changed elsewhere.", exact=True).wait_for()
    assert dialog.get_by_label("Comment", exact=True).input_value() == "My preserved draft"
    assert dialog.get_by_role("button", name="Save", exact=True).is_disabled()
    dialog.get_by_text("Concurrent new feedback", exact=True).wait_for()
    dialog.get_by_role("button", name="Keep mine", exact=True).click()
    dialog.get_by_role("button", name="Save", exact=True).click()
    dialog.wait_for(state="hidden")
    assert read_comments(project)["comments"][0]["text"] == "My preserved draft"
    page.goto("https://study.invalid/#home")
    page.get_by_role("button", name="Reset progress", exact=True).click()
    page.get_by_role("dialog", name="Reset progress?", exact=True).get_by_role(
        "button", name="Reset", exact=True
    ).click()
    page.goto("https://study.invalid/#bfs/content")
    page.locator('.comment-marker[data-open-count="1"]').wait_for()
    assert read_comments(project)["comments"][0]["text"] == "My preserved draft"
    open_notes(page)
    # Agent resolution is read back without rewriting a browser copy of the file.
    current = read_comments(project)
    done = SetStatus(
        op="status",
        id=note["id"],
        course_identity=current["course_identity"],
        expected_revision=current["revision"],
        status="resolved",
        resolution="Verified example",
    )
    change_comment(project, done)
    page.locator('.comment-marker[data-open-count="0"]').wait_for()
    page.get_by_role("button", name="Resolved", exact=True).click()
    page.get_by_text("Resolved · Verified example", exact=True).wait_for()
    page.get_by_role("button", name="Reopen", exact=True).click()
    page.locator('.comment-marker[data-open-count="1"]').wait_for()
    # Auto-sync external additions/deletions without replacing a focused existing row.
    row = page.locator(".comment-note").element_handle()
    more = page.get_by_label("More actions", exact=True)
    more.focus()
    current = read_comments(project)
    other = Create(
        id=uuid4(),
        op="create",
        course_identity=current["course_identity"],
        expected_revision=current["revision"],
        anchor=note["anchor"],
        text="Second note",
    )
    added = change_comment(project, other)
    page.locator('.comment-marker[data-open-count="2"]').wait_for()
    assert row.evaluate("element => element === document.querySelector('.comment-note')")
    assert page.evaluate("document.activeElement.matches('.comment-more > summary')")
    current = change_comment(
        project,
        Delete(
            op="delete",
            id=other.id,
            course_identity=added["course_identity"],
            expected_revision=added["revision"],
        ),
    )
    page.locator('.comment-marker[data-open-count="1"]').wait_for()
    assert row.evaluate("element => element === document.querySelector('.comment-note')")
    assert page.get_by_role("button", name="Refresh", exact=False).count() == 0
    assert page.locator(".view-bar .comment-marker, .view-actions, .content-comments").count() == 0
    # An unrelated write can be rebased once; a changed target needs an explicit choice.
    more.click()
    page.get_by_role("button", name="Edit", exact=True).click()
    dialog.get_by_label("Comment", exact=True).fill("Draft after unrelated update")
    other = Create(
        id=uuid4(),
        op="create",
        course_identity=current["course_identity"],
        expected_revision=current["revision"],
        anchor=note["anchor"],
        text="Unrelated update",
    )
    added = change_comment(project, other)
    dialog.get_by_role("button", name="Save", exact=True).click()
    dialog.wait_for(state="hidden")
    assert read_comments(project)["comments"][0]["text"] == "Draft after unrelated update"
    current = read_comments(project)
    change_comment(
        project,
        Delete(
            op="delete",
            id=other.id,
            course_identity=current["course_identity"],
            expected_revision=current["revision"],
        ),
    )
    page.locator('.comment-marker[data-open-count="1"]').wait_for()
    page.get_by_label("More actions", exact=True).click()
    page.get_by_role("button", name="Edit", exact=True).click()
    current = read_comments(project)
    change_comment(
        project,
        Edit(
            op="edit",
            id=note["id"],
            text="Latest note",
            course_identity=current["course_identity"],
            expected_revision=current["revision"],
        ),
    )
    dialog.get_by_text("Changed elsewhere.", exact=True).wait_for()
    dialog.get_by_role("button", name="Use latest", exact=True).click()
    assert dialog.get_by_label("Comment", exact=True).input_value() == "Latest note"
    dialog.get_by_role("button", name="Cancel", exact=True).click()
    # A missing quote stays recorded instead of being attached to a different passage.
    source = project / "study/content.json"
    original = source.read_bytes()
    value = json.loads(original)
    unit = next(unit for unit in value["units"] if unit["key"] == note["anchor"]["unit_key"])
    block = unit["blocks"][note["anchor"]["block_index"]]
    block["paragraphs"][0] = "A replacement explanation with a different opening."
    try:
        source.write_text(json.dumps(value), encoding="utf-8")
        build(project)
        page.reload()
        open_notes(page)
        page.get_by_text("Passage unavailable.", exact=True).wait_for()
        assert page.get_by_role("button", name="Show passage", exact=True).is_disabled()
        assert page.locator(".comment-note .comment-excerpt").is_visible()
        assert read_comments(project)["comments"][0]["anchor"]["quote"] == quote
    finally:
        source.write_bytes(original)
        build(project)
    page.get_by_label("More actions", exact=True).click()
    page.get_by_role("button", name="Delete", exact=True).click()
    page.get_by_role("dialog", name="Delete comment?", exact=True).get_by_role(
        "button", name="Delete", exact=True
    ).click()
    page.locator(".comment-marker").wait_for(state="hidden")
    assert read_comments(project)["comments"] == []
    # Deletion while editing preserves the draft and cannot silently recreate a note.
    current = read_comments(project)
    extra = Create(
        id=uuid4(),
        op="create",
        course_identity=current["course_identity"],
        expected_revision=current["revision"],
        anchor=note["anchor"],
        text="Temporary note",
    )
    added = change_comment(project, extra)
    page.locator('.comment-marker[data-open-count="1"]').wait_for()
    open_notes(page)
    page.get_by_label("More actions", exact=True).click()
    page.get_by_role("button", name="Edit", exact=True).click()
    dialog.get_by_label("Comment", exact=True).fill("Keep this unsaved text")
    change_comment(
        project,
        Delete(
            op="delete",
            id=extra.id,
            course_identity=added["course_identity"],
            expected_revision=added["revision"],
        ),
    )
    dialog.get_by_text("Removed elsewhere.", exact=True).wait_for()
    assert dialog.get_by_role("button", name="Save", exact=True).is_disabled()
    assert dialog.get_by_label("Comment", exact=True).input_value() == "Keep this unsaved text"
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden")
    assert read_comments(project)["comments"] == []
    page.reload()
    page.locator(".reading-material").first.wait_for()
