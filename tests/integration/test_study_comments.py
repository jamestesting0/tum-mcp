import json
import os
from pathlib import Path

import pytest
from study_comments_data import operation
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_comment_models import Anchor, Create, Delete, Edit, SetStatus
from tum_mcp.study_comments import change_comment, read_comments


def test_comments_are_private_project_files_and_compare_and_swap(project: Path) -> None:
    first = operation(project)
    assert not (project / ".tum-mcp/comments.json").exists()
    saved = change_comment(project, first)
    assert saved["comments"][0]["text"] == first.text
    file = project / ".tum-mcp/comments.json"
    if os.name != "nt":
        assert file.stat().st_mode & 0o077 == 0
    edit = Edit(
        op="edit",
        id=first.id,
        course_identity=first.course_identity,
        expected_revision=saved["revision"],
        text="Student's updated explanation request",
    )
    updated = change_comment(project, edit)
    old_resolution = SetStatus(
        op="status",
        id=first.id,
        course_identity=first.course_identity,
        expected_revision=saved["revision"],
        status="resolved",
        resolution="Verified",
    )
    with pytest.raises(CampusError) as caught:
        change_comment(project, old_resolution)
    assert caught.value.code == Code.STALE_RESULT
    assert read_comments(project) == updated
    assert not list((project / "study").glob("*comments*.json"))


def test_resolve_edit_reopens_and_delete_preserves_other_notes(project: Path) -> None:
    first = operation(project)
    saved = change_comment(project, first)
    second = operation(project)
    saved = change_comment(project, second)
    done = SetStatus(
        op="status",
        id=first.id,
        course_identity=first.course_identity,
        expected_revision=saved["revision"],
        status="resolved",
        resolution="Added an example",
    )
    saved = change_comment(project, done)
    saved = change_comment(
        project,
        Edit(
            op="edit",
            id=first.id,
            course_identity=first.course_identity,
            expected_revision=saved["revision"],
            text="Still unclear",
        ),
    )
    assert saved["comments"][0]["status"] == "open"
    assert saved["comments"][0]["resolution"] == ""
    saved = change_comment(
        project,
        Delete(
            op="delete",
            id=first.id,
            course_identity=first.course_identity,
            expected_revision=saved["revision"],
        ),
    )
    assert [item["id"] for item in saved["comments"]] == [str(second.id)]


def test_foreign_identity_and_damaged_records_are_preserved(project: Path) -> None:
    first = operation(project)
    with pytest.raises(CampusError) as caught:
        change_comment(project, first.model_copy(update={"course_identity": "0" * 64}))
    assert caught.value.code == Code.SCOPE_DENIED
    file = project / ".tum-mcp/comments.json"
    file.write_bytes(b"")
    with pytest.raises(CampusError):
        read_comments(project)
    assert file.read_bytes() == b""


def test_cli_handoff_reports_changed_content_and_requires_current_revision(
    project: Path, tmp_path: Path
) -> None:
    note = operation(project)
    saved = change_comment(project, note)
    source = project / "study/content.json"
    value = json.loads(source.read_bytes())
    value["units"][0]["summary"] += " Reviewed example."
    source.write_text(json.dumps(value), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["study", "comments", "list", str(project)])
    assert result.exit_code == 0, result.output
    listed = json.loads(result.output)
    assert listed["comments"][0]["content_state"] == "content_changed"
    resolution = tmp_path / "resolution.txt"
    resolution.write_text("Revised the explanation and checked it.", encoding="utf-8")
    args = [
        "study",
        "comments",
        "resolve",
        str(project),
        str(note.id),
        "--expected-revision",
        listed["revision"],
        "--resolution-file",
        str(resolution),
    ]
    assert runner.invoke(app, args).exit_code == 0
    assert (
        json.loads(runner.invoke(app, ["study", "comments", "list", str(project)]).output)[
            "comments"
        ]
        == []
    )
    before = (project / ".tum-mcp/comments.json").read_bytes()
    assert runner.invoke(app, args).exit_code != 0
    assert (project / ".tum-mcp/comments.json").read_bytes() == before
    assert saved["revision"] == listed["revision"]


def test_comment_symlink_cannot_escape(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "private.json"
    outside.write_text("preserved", encoding="utf-8")
    try:
        (project / ".tum-mcp/comments.json").symlink_to(outside)
    except OSError:
        pytest.skip("This Windows account cannot create symbolic links.")
    with pytest.raises(CampusError):
        read_comments(project)
    assert outside.read_text(encoding="utf-8") == "preserved"


def test_comment_listing_is_paged_without_losing_revision(project: Path) -> None:
    for _ in range(3):
        change_comment(project, operation(project))
    runner = CliRunner()
    args = ["study", "comments", "list", str(project), "--limit", "1"]
    first = json.loads(runner.invoke(app, args).output)
    second = json.loads(runner.invoke(app, args + ["--offset", "1"]).output)
    assert first["total"] == second["total"] == 3
    assert first["next_offset"] == 1 and second["next_offset"] == 2
    assert first["revision"] == second["revision"]
    assert first["comments"][0]["id"] != second["comments"][0]["id"]


def test_activity_targets_remain_filterable_and_legacy_content_notes_load(project: Path) -> None:
    first = operation(project)
    anchor = Anchor(
        **(
            first.anchor.model_dump()
            | {
                "view": "practice",
                "item_key": "degree-sum",
                "field": "prompt",
                "block_title": "Practice",
            }
        )
    )
    create = Create(**(first.model_dump() | {"anchor": anchor}))
    saved = change_comment(project, create)
    runner = CliRunner()
    listing = runner.invoke(app, ["study", "comments", "list", str(project), "--view", "practice"])
    assert listing.exit_code == 0
    assert json.loads(listing.output)["comments"][0]["anchor"]["item_key"] == "degree-sum"
    assert (
        json.loads(
            runner.invoke(
                app, ["study", "comments", "list", str(project), "--view", "content"]
            ).output
        )["comments"]
        == []
    )
    # Previously stored content comments need no migration or rewrite on read.
    content = operation(project)
    saved = change_comment(project, content)
    raw = project / ".tum-mcp/comments.json"
    document = json.loads(raw.read_bytes())
    document["comments"][1]["anchor"].pop("view")
    raw.write_text(json.dumps(document), encoding="utf-8")
    before = raw.read_bytes()
    assert read_comments(project)["comments"][1]["anchor"]["view"] == "content"
    assert raw.read_bytes() == before
    assert saved["comments"][0]["anchor"]["view"] == "practice"
