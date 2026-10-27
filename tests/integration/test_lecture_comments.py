import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import test_lecture_workspace as fixtures
from playwright.sync_api import Browser, expect
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_data import read_lectures
from tum_mcp.study_comment_models import Create, LectureAnchor
from tum_mcp.study_comments import change_comment, read_comments

lecture_project = fixtures.lecture_project
lecture_url = fixtures.lecture_url
course_browser = fixtures.course_browser


def create(root: Path, **changes) -> Create:
    document = read_comments(root)
    lecture = read_lectures(root).lectures[0]
    anchor = LectureAnchor(
        lecture_key=lecture.key,
        section_key=lecture.sections[0].key,
        semantic_revision=lecture.semantic_revision,
        quote="FIFO processes vertices already in the queue first.",
    ).model_copy(update=changes)
    return Create(
        op="create",
        id=uuid4(),
        text="Explain the ordering.",
        anchor=anchor,
        course_identity=document["course_identity"],
        expected_revision=document["revision"],
    )


@pytest.mark.parametrize("version", [1, 2])
def test_lecture_comment_upgrade_filter_and_receipt_independent_revision(
    lecture_project: Path, version: int
) -> None:
    from study_comments_data import operation

    root = lecture_project
    saved = change_comment(root, operation(root))
    path = root / ".tum-mcp/comments.json"
    payload = json.loads(path.read_text())
    payload["schema_version"] = version
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    read_comments(root)
    assert path.read_bytes() == before
    saved = change_comment(root, create(root))
    assert saved["schema_version"] == 3 and len(saved["comments"]) == 2
    lecture = read_lectures(root).lectures[0]
    notes = root / "study/lectures.json"
    value = json.loads(notes.read_text())
    value["lectures"][0]["checked_at"] = "2026-10-26T16:00:00Z"
    notes.write_text(json.dumps(value))
    result = CliRunner().invoke(
        app,
        ["study", "comments", "list", str(root), "--view", "lectures", "--lecture", lecture.key],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["comments"][0]["content_state"] == "current"
    value["lectures"][0]["overview"] += " A new explanation."
    notes.write_text(json.dumps(value))
    result = CliRunner().invoke(app, ["study", "comments", "list", str(root), "--view", "lectures"])
    assert json.loads(result.output)["comments"][0]["content_state"] == "content_changed"
    assert read_comments(root)["comments"][0] == saved["comments"][0]


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"lecture_key": "other"}, Code.SCOPE_DENIED),
        ({"section_key": "other"}, Code.SCOPE_DENIED),
        ({"semantic_revision": "0" * 64}, Code.STALE_RESULT),
    ],
)
def test_reject_foreign_or_stale_lecture_anchor_before_saving(
    lecture_project: Path, changes, code
) -> None:
    before = read_comments(lecture_project)
    with pytest.raises(CampusError) as caught:
        change_comment(lecture_project, create(lecture_project, **changes))
    assert caught.value.code == code
    assert read_comments(lecture_project) == before


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Explicit browser QA."
)
def test_select_save_reload_locate_and_ambiguous_passage_stays_unavailable(
    course_browser: Browser, lecture_url: str, lecture_project: Path, tmp_path: Path
) -> None:
    change_comment(lecture_project, create(lecture_project))
    context = course_browser.new_context()
    try:
        page = context.new_page()
        page.goto(lecture_url + "#lectures/bfs-lecture")
        text = page.locator(".lecture-material p").first
        text.evaluate("""element => {
          const range = document.createRange(); range.selectNodeContents(element);
          const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
          document.dispatchEvent(new Event('selectionchange'));
        }""")
        page.get_by_role("button", name="Comment", exact=True).click()
        page.get_by_role("textbox", name="Comment", exact=True).fill(
            "Show the queue before the next discovery."
        )
        page.get_by_role("button", name="Save", exact=True).click()
        expect(page.locator(".comment-marker")).to_be_visible()
        page.reload()
        page.locator(".comment-marker").wait_for()
        page.locator(".comment-marker").click()
        expect(
            page.get_by_text("Show the queue before the next discovery.", exact=True)
        ).to_be_visible()
        assert read_comments(lecture_project)["schema_version"] == 3
        capture = Path(os.environ.get("TUM_MCP_LECTURE_QA_PATH", str(tmp_path)))
        capture.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(capture / "lecture-comment.png"))
        # A duplicated quote without context has two exact matches; never choose one silently.
        page.locator(".lecture-material p").first.evaluate(
            "element => element.after(element.cloneNode(true))"
        )
        page.locator(".lecture-material").first.evaluate(
            "element => element.dispatchEvent(new Event("
            "'study-activity-change', { bubbles: true }))"
        )
        page.locator(".comment-marker").click()
        expect(page.get_by_text("Passage unavailable.", exact=True).first).to_be_visible()
        page.screenshot(path=str(capture / "lecture-comment-ambiguous.png"))
        page.reload()
        # Mutate persisted authored text and rebuild; old literal quote is absent.
        path = lecture_project / "study/lectures.json"
        payload = json.loads(path.read_text())
        payload["lectures"][0]["sections"][0]["blocks"][0]["paragraphs"][0] = (
            "Revised explanation with different wording."
        )
        path.write_text(json.dumps(payload))
        from tum_mcp.study_build import build

        build(lecture_project, publish=False)
        page.reload()
        page.locator(".comment-marker").click()
        expect(page.get_by_text("Passage unavailable.", exact=True).first).to_be_visible()
        # Time/source/figure controls cannot become selected prose anchors.
        assert page.locator(".citation-panel [data-comment-target]").count() == 0
    finally:
        context.close()
