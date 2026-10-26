import io
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pypdf import PdfWriter

from tum_mcp.errors import CampusError
from tum_mcp.studocu.courses import record_courses
from tum_mcp.studocu.imports import import_staged, stage
from tum_mcp.studocu.state import load_queue, plan, record_discovery
from tum_mcp.study_store import load_state
from tum_mcp.study_sync import sync


@pytest.fixture
def project_with_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    record_courses([{"course_id": 123, "institution_id": 92, "name": "Course"}])
    project = tmp_path / "course"
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "course": {
                    "key": "course",
                    "title": "Course",
                    "semester": "Winter",
                    "bindings": [{"key": "moodle", "provider": "moodle", "course_id": "1"}],
                },
                "coverage": [{"binding": "moodle", "status": "complete", "checked_at": "today"}],
                "resources": [
                    {
                        "key": "lecture",
                        "binding": "moodle",
                        "kind": "content",
                        "title": "Lecture",
                        "url": "https://example.org/lecture",
                        "text": "Notes",
                    }
                ],
            }
        )
    )
    sync(project, snapshot, course_input="Course")
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": []}))
    plan(project, selection)
    record_discovery(
        project, "123", [{"id": "42", "course_id": 123}, {"id": "43", "course_id": 123}]
    )
    selection.write_text(
        json.dumps(
            {
                "course_id": "123",
                "documents": [
                    {
                        "document_id": "42",
                        "decision": "include",
                        "reason": "Relevant mock examination",
                        "title": "Mock",
                        "url": "https://www.studocu.com/de/document/42",
                        "group": "exams",
                        "document_type": "mock",
                        "year": 2024,
                        "lecturer": "Synthetic lecturer",
                        "language": "en",
                    }
                ],
            }
        )
    )
    plan(project, selection)
    return project


def test_first_plan_binds_course_before_search_or_download(project_with_selection: Path) -> None:
    state = load_state(project_with_selection)
    binding = next(item for item in state.course.bindings if item.provider == "studocu")
    assert binding.course_id == "123"
    assert next(item for item in state.coverage if item.binding == binding.key).status == "partial"
    assert not any(item.resource.binding == binding.key for item in state.resources)


def test_different_course_requires_explicit_confirmation(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = tmp_path / "different"
    sync(project, tmp_path / "snapshot.json", course_input="Course")
    record_courses([{"course_id": 456, "institution_id": 92, "name": "Different Course"}])
    selection = tmp_path / "different-selection.json"
    selection.write_text(json.dumps({"course_id": "456", "documents": []}))
    with pytest.raises(CampusError):
        plan(project, selection)
    assert all(item.provider != "studocu" for item in load_state(project).course.bindings)
    selection.write_text(
        json.dumps({"course_id": "456", "confirmed_course": True, "documents": []})
    )
    plan(project, selection)
    assert (
        next(
            item for item in load_state(project).course.bindings if item.provider == "studocu"
        ).course_id
        == "456"
    )


@pytest.mark.parametrize("missing", ["decision", "reason"])
def test_selection_requires_explicit_decision_and_reason(
    project_with_selection: Path, tmp_path: Path, missing: str
) -> None:
    entry = {
        "document_id": "42",
        "title": "Mock",
        "url": "https://www.studocu.com/de/document/42",
        "group": "exams",
        "decision": "include",
        "reason": "Relevant mock exam",
    }
    entry.pop(missing)
    selection = tmp_path / "incomplete-selection.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [entry]}))
    with pytest.raises(CampusError):
        plan(project_with_selection, selection)


def test_import_preserves_original_and_campus_sources(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    source = tmp_path / "browser-save"
    source.write_bytes(buffer.getvalue())
    old = load_state(project)
    staged = stage(project, "42", source)
    result = import_staged(project, "42", staged)
    assert result["identity_basis"] == "user_selected_file"
    assert (
        project / "materials/studocu/exams/material-studocu-42.pdf"
    ).read_bytes() == buffer.getvalue()
    new = load_state(project)
    source = next(
        item.resource.studocu for item in new.resources if item.resource.key == "studocu-42"
    )
    assert source.lecturer == "Synthetic lecturer" and source.language == "en"
    assert next(r for r in new.resources if r.resource.key == "lecture") == old.resources[0]
    assert next(c for c in new.coverage if c.binding == "moodle") == next(
        c for c in old.coverage if c.binding == "moodle"
    )
    assert load_queue(project).documents[0].state == "imported"
    assert import_staged(project, "42", staged)["state"] == "already_imported"
    assert load_state(project).generation == new.generation
    monkeypatch.setattr("tum_mcp.studocu.server.require_enabled", lambda: None)
    from tum_mcp.studocu.server import studocu_get_document

    view = studocu_get_document(str(project), 42, include_images=True)
    assert view.structured_content["pages"][0]["number"] == 1
    assert any(item.type == "image" for item in view.content)


def test_import_denies_wrong_document_or_unsafe_staging(
    project_with_selection: Path, tmp_path: Path
) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    name = stage(project_with_selection, "42", file)
    with pytest.raises(CampusError):
        import_staged(project_with_selection, "43", name)
    with pytest.raises(CampusError):
        import_staged(project_with_selection, "42", "../../outside.pdf")
    assert load_queue(project_with_selection).documents[0].state == "downloaded"


def test_unverified_and_wrong_course_candidates_are_not_selectable(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    record_discovery(project, "123", [{"id": "99", "course_id": 999}])
    selection = tmp_path / "wrong.json"
    selection.write_text(
        json.dumps(
            {
                "course_id": "123",
                "documents": [
                    {
                        "document_id": "99",
                        "decision": "include",
                        "reason": "Candidate from another course",
                        "title": "Wrong course",
                        "url": "https://www.studocu.com/de/document/99",
                        "group": "exams",
                    }
                ],
            }
        )
    )
    with pytest.raises(CampusError):
        plan(project, selection)
    record_courses([{"course_id": 999, "institution_id": 12}])
    selection.write_text(json.dumps({"course_id": "999", "documents": []}))
    with pytest.raises(CampusError):
        plan(project, selection)


def test_review_decision_can_be_selected_later(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    item = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation"})
    )
    item.update({"decision": "review", "reason": "Course year needs checking"})
    selection = tmp_path / "review.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    plan(project, selection)
    from tum_mcp.studocu.state import request_browser_download

    with pytest.raises(CampusError):
        request_browser_download(project, "42")
    item.update({"decision": "include", "reason": "Confirmed relevant mock exam"})
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    plan(project, selection)
    assert request_browser_download(project, "42").state == "action_required"


def test_same_year_and_type_duplicates_share_one_original_via_alias(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    queue = load_queue(project)
    first = queue.documents[0].model_dump(
        exclude={"state", "duplicate_of", "staged_name", "validation"}
    )
    second = first | {"document_id": "43", "url": "https://www.studocu.com/de/document/43"}
    selection = tmp_path / "more.json"
    selection.write_text(json.dumps({"course_id": queue.course_id, "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", file))
    result = import_staged(project, "43", stage(project, "43", file))
    assert result["state"] == "duplicate" and result["duplicate_of"] == "42"
    assert {item.resource.key for item in load_state(project).resources} >= {
        "studocu-42",
        "studocu-43",
    }
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-43"].alias_of == "studocu-42"
    assert sources["studocu-43"].path is None
    assert (project / sources["studocu-42"].path).read_bytes() == file.read_bytes()
    assert not (project / "materials/studocu/exams/material-studocu-43.pdf").exists()
    assert not list((project / ".tum-mcp/studocu/incoming").glob("*.pdf"))
    assert load_queue(project).documents[1].duplicate_of == "42"


def duplicate_pair(project: Path, tmp_path: Path) -> Path:
    first = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    second = first | {"document_id": "43", "url": "https://www.studocu.com/de/document/43"}
    selection = tmp_path / "pair.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "pair.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    for document in ("42", "43"):
        import_staged(project, document, stage(project, document, pdf))
    return pdf


@pytest.mark.parametrize("document_id", ["42", "43"])
@pytest.mark.parametrize(
    "field,value", [("lecturer", "New lecturer"), ("language", "de"), ("raw_category", "Exam")]
)
def test_metadata_changes_do_not_split_identical_aliases(
    project_with_selection: Path, tmp_path: Path, document_id: str, field: str, value: str
) -> None:
    project = project_with_selection
    duplicate_pair(project, tmp_path)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    next(item for item in entries if item["document_id"] == document_id)[field] = value
    selection = tmp_path / "metadata.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert getattr(sources[f"studocu-{document_id}"].resource.studocu, field) == value
    assert sources["studocu-43"].alias_of == "studocu-42"
    assert sources["studocu-43"].path is None
    assert not (project / "materials/studocu/exams/material-studocu-43.pdf").exists()


@pytest.mark.parametrize("document_id", ["42", "43"])
def test_lost_import_receipt_can_be_recreated_from_the_original(
    project_with_selection: Path, tmp_path: Path, document_id: str
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    document = next(
        item for item in load_queue(project).documents if item.document_id == document_id
    )
    receipt = project / ".tum-mcp/studocu/incoming" / f"{document.staged_name}.json"
    receipt.unlink()
    staged = stage(project, document_id, pdf)
    assert import_staged(project, document_id, staged)["state"] == "already_imported"
    assert not list((project / ".tum-mcp/studocu/incoming").glob("*.pdf"))


def test_pending_receipt_is_not_accepted_as_a_completed_import(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    document = next(item for item in load_queue(project).documents if item.document_id == "43")
    receipt = project / ".tum-mcp/studocu/incoming" / f"{document.staged_name}.json"
    data = json.loads(receipt.read_text())
    data["validation"] = "pending"
    receipt.write_text(json.dumps(data))
    with pytest.raises(CampusError):
        import_staged(project, "43", document.staged_name)
    assert import_staged(project, "43", stage(project, "43", pdf))["state"] == "already_imported"
    assert json.loads(receipt.read_text())["validation"] == "pending"


@pytest.mark.parametrize("document_id", ["42", "43"])
def test_reimport_cleans_unchanged_legacy_staging_copy(
    project_with_selection: Path, tmp_path: Path, document_id: str
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    document = next(
        item for item in load_queue(project).documents if item.document_id == document_id
    )
    staged_file = project / ".tum-mcp/studocu/incoming" / document.staged_name
    staged_file.write_bytes(pdf.read_bytes())
    assert import_staged(project, document_id, document.staged_name)["state"] == "already_imported"
    assert not staged_file.exists()


@pytest.mark.parametrize("document_id", ["42", "43"])
def test_reimport_preserves_edited_legacy_staging_copy(
    project_with_selection: Path, tmp_path: Path, document_id: str
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    document = next(
        item for item in load_queue(project).documents if item.document_id == document_id
    )
    staged_file = project / ".tum-mcp/studocu/incoming" / document.staged_name
    staged_file.write_bytes(b"user edit")
    new_name = stage(project, document_id, pdf)
    assert new_name != document.staged_name
    assert import_staged(project, document_id, new_name)["state"] == "already_imported"
    assert staged_file.read_bytes() == b"user edit"


def test_alias_read_preserves_its_citation_and_detects_edits(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.studocu.server import studocu_get_document

    project = project_with_selection
    duplicate_pair(project, tmp_path)
    monkeypatch.setattr("tum_mcp.studocu.server.require_enabled", lambda: None)
    result = studocu_get_document(str(project), 43)
    assert result.structured_content["source_url"].endswith("/43")
    canonical = project / "materials/studocu/exams/material-studocu-42.pdf"
    canonical.write_bytes(b"user edit")
    with pytest.raises(CampusError):
        studocu_get_document(str(project), 43)


def test_alias_works_in_study_exercises_and_handbook_without_exporting_private_content(
    project_with_selection: Path, tmp_path: Path
) -> None:
    from tum_mcp.course_context import context_review
    from tum_mcp.exercise_data import read_exercises, stale_exercises
    from tum_mcp.study_build import build, read_content, stale_units
    from tum_mcp.study_publish_site import export_site

    project = project_with_selection
    duplicate_pair(project, tmp_path)
    state = load_state(project)
    source = next(item for item in state.resources if item.resource.key == "studocu-43")
    fixtures = Path(__file__).parents[1] / "fixtures"
    content = json.loads((fixtures / "course_app/content.json").read_text())
    content["course_key"] = "course"
    content["units"] = [next(unit for unit in content["units"] if unit["key"] == "weighted")]
    exercises = json.loads((fixtures / "exercises.json").read_text())
    exercises["course_key"] = "course"

    def cite_alias(value):
        if isinstance(value, list):
            return [cite_alias(item) for item in value]
        if isinstance(value, dict):
            return {
                key: (
                    [{"key": "studocu-43", "sha256": source.sha256}]
                    if item and isinstance(item[0], dict)
                    else ["studocu-43"]
                )
                if key == "sources"
                else cite_alias(item)
                for key, item in value.items()
            }
        return value

    app = project / "app"
    app.mkdir(exist_ok=True)
    (app / "content.json").write_text(json.dumps(cite_alias(content)))
    (app / "exercises.json").write_text(json.dumps(cite_alias(exercises)))
    build(project, publish=False)
    data = (app / "data.mjs").read_text()
    assert "https://www.studocu.com/de/document/43" in data
    with pytest.raises(CampusError):
        export_site(project, include_exercises=True)
    handbook = project / ".tum-mcp/course.md"
    handbook.write_text(
        f"---\ncourse_key: course\nsemester: Winter\nreviewed_generation: {state.generation}\n"
        f"reviewed_sources:\n  studocu-43: {source.sha256}\n---\n# Course\n"
    )
    assert context_review(project, state).status == "current"
    (project / "materials/studocu/exams/material-studocu-42.pdf").write_bytes(b"edited")
    assert stale_units(project, state, read_content(project))
    assert stale_exercises(project, state, read_exercises(project))
    assert context_review(project, state).status == "stale"


@pytest.mark.parametrize("document_id", ["42", "43"])
def test_refresh_separates_aliases_without_losing_the_old_original(
    project_with_selection: Path, tmp_path: Path, document_id: str
) -> None:
    project = project_with_selection
    old = duplicate_pair(project, tmp_path).read_bytes()
    queue = load_queue(project)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in queue.documents
    ]
    next(item for item in entries if item["document_id"] == document_id)["refresh"] = True
    selection = tmp_path / "refresh-alias.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    new = tmp_path / "new.pdf"
    with new.open("wb") as output:
        writer.write(output)
    import_staged(project, document_id, stage(project, document_id, new))
    sources = {item.resource.key: item for item in load_state(project).resources}
    changed = sources[f"studocu-{document_id}"]
    other = sources["studocu-43" if document_id == "42" else "studocu-42"]
    assert changed.alias_of is None and other.alias_of is None
    assert (project / changed.path).read_bytes() == new.read_bytes()
    assert (project / other.path).read_bytes() == old


@pytest.mark.parametrize("staged_before_reclassification", [False, True])
def test_reclassifying_an_existing_document_during_refresh_keeps_import_resumable(
    project_with_selection: Path, tmp_path: Path, staged_before_reclassification: bool
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    selection = tmp_path / "refresh-change.json"
    entries[0]["refresh"] = True
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    with pdf.open("wb") as output:
        writer.write(output)
    staged = stage(project, "42", pdf) if staged_before_reclassification else None
    entries[0]["refresh"] = False
    entries[0]["group"] = "summaries"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    source = next(
        item for item in load_state(project).resources if item.resource.key == "studocu-42"
    )
    assert source.resource.studocu.storage_group == "summaries"
    assert next(
        item for item in load_queue(project).documents if item.document_id == "42"
    ).state == ("downloaded" if staged_before_reclassification else "pending")
    assert import_staged(project, "42", staged or stage(project, "42", pdf))["state"] == "imported"


@pytest.mark.parametrize("document_id", ["42", "43"])
def test_reclassifying_either_document_safely_separates_aliases(
    project_with_selection: Path, tmp_path: Path, document_id: str
) -> None:
    project = project_with_selection
    old = duplicate_pair(project, tmp_path).read_bytes()
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    next(item for item in entries if item["document_id"] == document_id)["group"] = "summaries"
    selection = tmp_path / "reclassify-alias.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    for key in ("studocu-42", "studocu-43"):
        assert sources[key].alias_of is None
        assert (project / sources[key].path).read_bytes() == old
    assert sources[f"studocu-{document_id}"].path.startswith("materials/studocu/summaries/")


@pytest.mark.parametrize("edited", [False, True])
def test_existing_duplicate_is_consolidated_only_if_both_files_are_unchanged(
    project_with_selection: Path, tmp_path: Path, edited: bool
) -> None:
    project = project_with_selection
    body = duplicate_pair(project, tmp_path).read_bytes()
    state_file = project / ".tum-mcp/state.json"
    state = json.loads(state_file.read_text())
    legacy = next(item for item in state["resources"] if item["resource"]["key"] == "studocu-43")
    legacy["alias_of"] = None
    legacy["path"] = "materials/studocu/exams/material-studocu-43.pdf"
    legacy_path = project / legacy["path"]
    legacy_path.write_bytes(b"user edits" if edited else body)
    state_file.write_text(json.dumps(state))
    queue = load_queue(project)
    for item in queue.documents:
        (project / ".tum-mcp/studocu/incoming" / item.staged_name).write_bytes(body)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in queue.documents
    ]
    selection = tmp_path / "resume.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    source = next(
        item for item in load_state(project).resources if item.resource.key == "studocu-43"
    )
    if edited:
        assert source.alias_of is None
        assert legacy_path.read_bytes() == b"user edits"
        assert (project / ".tum-mcp/studocu/incoming" / queue.documents[1].staged_name).exists()
    else:
        assert source.alias_of == "studocu-42"
        assert not legacy_path.exists()
        assert not list((project / ".tum-mcp/studocu/incoming").glob("*.pdf"))


@pytest.mark.parametrize(
    "field,value", [("group", "summaries"), ("year", 2025), ("document_type", "solution")]
)
def test_simultaneous_matching_reclassification_keeps_alias(
    project_with_selection: Path, tmp_path: Path, field: str, value: str | int
) -> None:
    project = project_with_selection
    body = duplicate_pair(project, tmp_path).read_bytes()
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    for item in entries:
        item[field] = value
    selection = tmp_path / "both-groups.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-43"].alias_of == "studocu-42"
    assert sources["studocu-43"].path is None
    assert (project / sources["studocu-42"].path).read_bytes() == body


@pytest.mark.parametrize(
    "changes", [{"year": 2023}, {"year": None}, {"document_type": "solution"}, {"group": "other"}]
)
def test_uncertain_or_distinct_documents_keep_separate_originals(
    project_with_selection: Path, tmp_path: Path, changes: dict
) -> None:
    project = project_with_selection
    first = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    second = (
        first | {"document_id": "43", "url": "https://www.studocu.com/de/document/43"} | changes
    )
    selection = tmp_path / "distinct.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "same.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    for document in ("42", "43"):
        assert (
            import_staged(project, document, stage(project, document, pdf))["state"] == "imported"
        )
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-42"].alias_of is sources["studocu-43"].alias_of is None
    assert sources["studocu-42"].path != sources["studocu-43"].path


def test_corrected_metadata_consolidates_previously_uncertain_matches(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    first = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    second = first | {
        "document_id": "43",
        "url": "https://www.studocu.com/de/document/43",
        "year": None,
    }
    selection = tmp_path / "uncertain.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "uncertain.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    for doc_id in ("42", "43"):
        import_staged(project, doc_id, stage(project, doc_id, pdf))
    second["year"] = 2024
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-43"].alias_of == "studocu-42"
    assert not (project / "materials/studocu/exams/material-studocu-43.pdf").exists()


def test_group_change_consolidates_with_an_existing_matching_original(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    first = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    second = first | {
        "document_id": "43",
        "url": "https://www.studocu.com/de/document/43",
        "group": "other",
    }
    selection = tmp_path / "different-group.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "same-bytes.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    for doc_id in ("42", "43"):
        import_staged(project, doc_id, stage(project, doc_id, pdf))
    second["group"] = "exams"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-43"].alias_of == "studocu-42"
    assert not (project / "materials/studocu/other/material-studocu-43.pdf").exists()
    assert not (project / "materials/studocu/exams/material-studocu-43.pdf").exists()


def test_group_consolidation_rolls_back_if_retained_original_changes(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    selection = tmp_path / "rollback-consolidation.json"
    entries[1]["group"] = "other"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    before = (project / ".tum-mcp/state.json").read_bytes()
    entries[1]["group"] = "exams"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    canonical = project / "materials/studocu/exams/material-studocu-42.pdf"
    original_writer = study_store.private_write
    changed = False

    def edit_during_commit(path, value):
        nonlocal changed
        original_writer(path, value)
        if path.name == "state.json" and not changed:
            changed = True
            canonical.write_bytes(b"external edit")

    monkeypatch.setattr(study_store, "private_write", edit_during_commit)
    with pytest.raises(CampusError):
        plan(project, selection)
    assert (project / ".tum-mcp/state.json").read_bytes() == before
    assert canonical.read_bytes() == b"external edit"
    assert (
        project / "materials/studocu/other/material-studocu-43.pdf"
    ).read_bytes() == pdf.read_bytes()
    assert not (project / "materials/studocu/exams/material-studocu-43.pdf").exists()


def test_batch_moves_of_previously_separate_matches_share_the_new_original(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    first = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    second = first | {
        "document_id": "43",
        "url": "https://www.studocu.com/de/document/43",
        "group": "other",
    }
    selection = tmp_path / "both-move.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "same.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    for doc_id in ("42", "43"):
        import_staged(project, doc_id, stage(project, doc_id, pdf))
    first["group"] = second["group"] = "summaries"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-43"].alias_of == "studocu-42"
    assert (project / sources["studocu-42"].path).read_bytes() == pdf.read_bytes()
    assert not (project / "materials/studocu/summaries/material-studocu-43.pdf").exists()


def test_batch_move_preserves_external_edit_and_restores_previous_originals(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    project = project_with_selection
    first = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    second = first | {
        "document_id": "43",
        "url": "https://www.studocu.com/de/document/43",
        "group": "other",
    }
    selection = tmp_path / "batch-rollback.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "same.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    for doc_id in ("42", "43"):
        import_staged(project, doc_id, stage(project, doc_id, pdf))
    original_state = (project / ".tum-mcp/state.json").read_bytes()
    first["group"] = second["group"] = "summaries"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    new_path = project / "materials/studocu/summaries/material-studocu-42.pdf"
    write = study_store.private_write
    changed = False

    def edit_during_commit(path, value):
        nonlocal changed
        write(path, value)
        if path.name == "queue.json" and not changed:
            changed = True
            new_path.write_bytes(b"external edit")

    monkeypatch.setattr(study_store, "private_write", edit_during_commit)
    with pytest.raises(CampusError):
        plan(project, selection)
    assert (project / ".tum-mcp/state.json").read_bytes() == original_state
    assert new_path.read_bytes() == b"external edit"
    assert (
        project / "materials/studocu/exams/material-studocu-42.pdf"
    ).read_bytes() == pdf.read_bytes()
    assert (
        project / "materials/studocu/other/material-studocu-43.pdf"
    ).read_bytes() == pdf.read_bytes()


def test_alias_promotion_rolls_back_if_inventory_write_fails(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    project = project_with_selection
    body = duplicate_pair(project, tmp_path).read_bytes()
    state_before = (project / ".tum-mcp/state.json").read_bytes()
    queue_before = (project / ".tum-mcp/studocu/queue.json").read_bytes()
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    entries[0]["group"] = "summaries"
    selection = tmp_path / "change.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    write = study_store.private_write

    def fail_state(path, value):
        if path.name == "state.json":
            raise OSError("synthetic interruption")
        write(path, value)

    monkeypatch.setattr(study_store, "private_write", fail_state)
    with pytest.raises(CampusError):
        plan(project, selection)
    assert (project / ".tum-mcp/state.json").read_bytes() == state_before
    assert (project / ".tum-mcp/studocu/queue.json").read_bytes() == queue_before
    assert (project / "materials/studocu/exams/material-studocu-42.pdf").read_bytes() == body
    assert not (project / "materials/studocu/exams/material-studocu-43.pdf").exists()
    assert not (project / "materials/studocu/summaries/material-studocu-42.pdf").exists()


@pytest.mark.parametrize(
    "interrupt_at", ["studocu-42.json", "material-studocu-43.pdf", "state.json", "queue.json"]
)
def test_interrupted_alias_promotion_resumes_without_another_download(
    project_with_selection: Path, tmp_path: Path, interrupt_at: str
) -> None:
    project = project_with_selection
    body = duplicate_pair(project, tmp_path).read_bytes()
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    entries[0]["group"] = "summaries"
    selection = tmp_path / "resume-promotion.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    child = """import os, sys
from pathlib import Path
from tum_mcp import study_store
from tum_mcp.studocu.state import plan
write = study_store.private_write
def interrupt(path, data):
    write(path, data)
    if path.name == sys.argv[3]: os._exit(73)
study_store.private_write = interrupt
plan(Path(sys.argv[1]), Path(sys.argv[2]))
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", child, str(project), str(selection), interrupt_at], check=False
    )
    assert result.returncode == 73
    plan(project, selection)
    state = {item.resource.key: item for item in load_state(project).resources}
    assert (project / state["studocu-42"].path).read_bytes() == body
    assert (project / state["studocu-43"].path).read_bytes() == body
    assert not list((project / ".tum-mcp/studocu/promotions").glob("*.json"))
    assert not (project / "materials/studocu/exams/material-studocu-42.pdf").exists()


def test_alias_import_preserves_staging_if_original_changes_during_commit(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    queue = load_queue(project)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in queue.documents
    ]
    record_discovery(project, "123", [{"id": "44", "course_id": 123}])
    entries.append(
        entries[0] | {"document_id": "44", "url": "https://www.studocu.com/de/document/44"}
    )
    selection = tmp_path / "third.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    staged = stage(project, "44", pdf)
    original = project / "materials/studocu/exams/material-studocu-42.pdf"
    writer = study_store.private_write
    edited = False

    def change_original(path, value):
        nonlocal edited
        writer(path, value)
        if path.name == "queue.json" and not edited:
            edited = True
            original.write_bytes(b"external edit")

    monkeypatch.setattr(study_store, "private_write", change_original)
    with pytest.raises(CampusError):
        import_staged(project, "44", staged)
    assert original.read_bytes() == b"external edit"
    assert (project / ".tum-mcp/studocu/incoming" / staged).read_bytes() == pdf.read_bytes()
    assert all(item.resource.key != "studocu-44" for item in load_state(project).resources)


@pytest.mark.parametrize("invalid", ["cycle", "different_hash", "missing_target", "shared_path"])
def test_invalid_alias_inventory_is_rejected(
    project_with_selection: Path, tmp_path: Path, invalid: str
) -> None:
    from pydantic import ValidationError

    from tum_mcp.study_models import StudyState

    project = project_with_selection
    duplicate_pair(project, tmp_path)
    data = load_state(project).model_dump(mode="json")
    original = next(item for item in data["resources"] if item["resource"]["key"] == "studocu-42")
    alias = next(item for item in data["resources"] if item["resource"]["key"] == "studocu-43")
    if invalid == "cycle":
        original["path"] = None
        original["alias_of"] = "studocu-43"
    elif invalid == "different_hash":
        alias["sha256"] = alias["resource"]["studocu"]["file_sha256"] = "f" * 64
    elif invalid == "missing_target":
        alias["alias_of"] = "studocu-999"
    else:
        alias["path"] = original["path"]
    with pytest.raises(ValidationError):
        StudyState.model_validate(data)


def test_consolidating_a_legacy_duplicate_retargets_existing_aliases(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    record_discovery(project, "123", [{"id": "44", "course_id": 123}])
    entries.append(
        entries[0] | {"document_id": "44", "url": "https://www.studocu.com/de/document/44"}
    )
    selection = tmp_path / "three.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    import_staged(project, "44", stage(project, "44", pdf))
    state_path = project / ".tum-mcp/state.json"
    data = json.loads(state_path.read_text())
    third = next(item for item in data["resources"] if item["resource"]["key"] == "studocu-44")
    third["alias_of"] = None
    third["path"] = "materials/studocu/exams/material-studocu-44.pdf"
    (project / third["path"]).write_bytes(pdf.read_bytes())
    state_path.write_text(json.dumps(data))
    queue_path = project / ".tum-mcp/studocu/queue.json"
    queue = json.loads(queue_path.read_text())
    for document in queue["documents"]:
        if document["document_id"] == "42":
            document.update({"state": "duplicate", "duplicate_of": "44"})
        if document["document_id"] == "44":
            document.update({"state": "imported", "duplicate_of": None})
    queue_path.write_text(json.dumps(queue))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-42"].alias_of == sources["studocu-43"].alias_of == "studocu-44"
    assert not (project / "materials/studocu/exams/material-studocu-42.pdf").exists()
    assert (project / third["path"]).read_bytes() == pdf.read_bytes()


def test_refreshing_original_promotes_one_alias_and_retargets_the_others(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    old = pdf.read_bytes()
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    record_discovery(project, "123", [{"id": "44", "course_id": 123}])
    entries.append(
        entries[0] | {"document_id": "44", "url": "https://www.studocu.com/de/document/44"}
    )
    selection = tmp_path / "three-refresh.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    import_staged(project, "44", stage(project, "44", pdf))
    entries[0]["refresh"] = True
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    with pdf.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", pdf))
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-43"].alias_of is None
    assert sources["studocu-44"].alias_of == "studocu-43"
    assert (project / sources["studocu-43"].path).read_bytes() == old
    assert (project / sources["studocu-42"].path).read_bytes() == pdf.read_bytes()
    queue = {item.document_id: item for item in load_queue(project).documents}
    assert queue["43"].state == "imported" and queue["44"].duplicate_of == "43"


def test_partial_family_reclassification_preserves_each_matching_alias(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    pdf = duplicate_pair(project, tmp_path)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    record_discovery(project, "123", [{"id": "44", "course_id": 123}])
    entries.append(
        entries[0] | {"document_id": "44", "url": "https://www.studocu.com/de/document/44"}
    )
    selection = tmp_path / "partial-move.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    import_staged(project, "44", stage(project, "44", pdf))
    entries[0]["group"] = entries[1]["group"] = "summaries"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert sources["studocu-43"].alias_of == "studocu-42"
    assert sources["studocu-44"].alias_of is None
    assert (project / sources["studocu-42"].path).read_bytes() == pdf.read_bytes()
    assert (project / sources["studocu-44"].path).read_bytes() == pdf.read_bytes()
    assert not (project / "materials/studocu/summaries/material-studocu-43.pdf").exists()


def test_search_records_course_scoped_discovery(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.studocu.server import studocu_search_materials

    monkeypatch.setattr("tum_mcp.studocu.server.require_enabled", lambda: None)
    monkeypatch.setattr(
        "tum_mcp.studocu.server.search",
        lambda *args: {
            "data": {"documents": [{"id": "55", "course_id": 123}, {"id": "56", "course_id": 999}]},
            "coverage": "partial",
        },
    )
    result = studocu_search_materials(str(project_with_selection), ["mock exam"])
    assert result["coverage"] == "partial"
    from tum_mcp.studocu.state import load_discovery

    receipt = load_discovery(project_with_selection)
    assert (
        receipt.searches[-1].query,
        receipt.searches[-1].limit,
        receipt.searches[-1].returned,
    ) == ("mock exam", 50, 2)
    selection = tmp_path / "new.json"
    selection.write_text(
        json.dumps(
            {
                "course_id": "123",
                "documents": [
                    {
                        "document_id": "55",
                        "decision": "include",
                        "reason": "Relevant mock examination",
                        "title": "Mock",
                        "url": "https://www.studocu.com/de/document/55",
                        "group": "exams",
                    }
                ],
            }
        )
    )
    plan(project_with_selection, selection)
    wrong = json.loads(selection.read_text())
    wrong["documents"][0].update(
        {"document_id": "56", "url": "https://www.studocu.com/de/document/56"}
    )
    selection.write_text(json.dumps(wrong))
    with pytest.raises(CampusError):
        plan(project_with_selection, selection)


def test_explicit_refresh_preserves_original_version(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    file = tmp_path / "original.pdf"
    first = PdfWriter()
    first.add_blank_page(width=200, height=200)
    with file.open("wb") as output:
        first.write(output)
    old = file.read_bytes()
    original = import_staged(project, "42", stage(project, "42", file))
    newer = PdfWriter()
    newer.add_blank_page(width=200, height=200)
    newer.add_blank_page(width=200, height=200)
    with file.open("wb") as output:
        newer.write(output)
    with pytest.raises(CampusError):
        stage(project, "42", file)
    state = load_state(project)
    source = next(item.resource for item in state.resources if item.resource.key == "studocu-42")
    direct = source.model_dump(mode="json")
    direct["source_file"] = file.name
    direct["studocu"]["file_sha256"] = "0" * 64
    direct["studocu"]["page_count"] = 2
    bypass = tmp_path / "bypass.json"
    bypass.write_text(
        json.dumps(
            {
                "course": state.course.model_dump(mode="json"),
                "coverage": [{"binding": "studocu", "status": "partial", "checked_at": "now"}],
                "retained_bindings": ["moodle"],
                "resources": [direct],
            }
        )
    )
    with pytest.raises(CampusError):
        sync(project, bypass)
    entry = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation"})
    )
    entry["refresh"] = True
    selection = tmp_path / "refresh.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [entry]}))
    plan(project, selection)
    staged = stage(project, "42", file)
    assert import_staged(project, "42", staged)["pages"] == 2
    saved = project / ".tum-mcp/studocu/history/42" / f"{original['sha256']}.pdf"
    assert saved.read_bytes() == old
    assert (
        project / "materials/studocu/exams/material-studocu-42.pdf"
    ).read_bytes() == file.read_bytes()


def test_concurrent_imports_reconcile_latest_state(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    queue = load_queue(project)
    first = queue.documents[0].model_dump(
        exclude={"state", "duplicate_of", "staged_name", "validation"}
    )
    second = first | {"document_id": "43", "url": "https://www.studocu.com/de/document/43"}
    selection = tmp_path / "both.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [first, second]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    staged = [(doc, stage(project, doc, file)) for doc in ("42", "43")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: import_staged(project, *pair), staged))
    assert {item["state"] for item in results} == {"imported", "duplicate"}
    assert {item.resource.key for item in load_state(project).resources} >= {
        "studocu-42",
        "studocu-43",
    }


def test_failed_queue_write_rolls_back_material_and_state(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    staged = stage(project, "42", file)
    before = load_state(project)
    write = study_store.private_write

    def fail_queue(path: Path, data: bytes) -> None:
        if path.name == "queue.json":
            raise OSError("synthetic interruption")
        write(path, data)

    with monkeypatch.context() as context:
        context.setattr(study_store, "private_write", fail_queue)
        with pytest.raises(CampusError):
            import_staged(project, "42", staged)
    assert load_state(project) == before
    assert load_queue(project).documents[0].state == "downloaded"
    assert not (project / "materials/studocu/exams/material-studocu-42.pdf").exists()
    assert import_staged(project, "42", staged)["state"] == "imported"


def test_staged_download_resumes_and_uncertain_outcome_requires_review(
    project_with_selection: Path, tmp_path: Path
) -> None:
    from tum_mcp.studocu.state import mark_outcome, request_browser_download

    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    staged = stage(project, "42", file)
    current = request_browser_download(project, "42")
    assert current.state == "downloaded" and current.staged_name == staged
    mark_outcome(project, "42", "outcome_unknown")
    with pytest.raises(CampusError):
        request_browser_download(project, "42")
    mark_outcome(project, "42", "pending")
    assert request_browser_download(project, "42").state == "action_required"


def test_browser_acquisition_is_claimed_once_until_explicit_recovery(
    project_with_selection: Path,
) -> None:
    from tum_mcp.studocu.state import mark_outcome

    project = project_with_selection
    first = mark_outcome(project, "42", "acquiring")
    assert first.attempt_id is not None
    with pytest.raises(CampusError):
        mark_outcome(project, "42", "acquiring")
    mark_outcome(project, "42", "outcome_unknown")
    with pytest.raises(CampusError):
        mark_outcome(project, "42", "acquiring")
    mark_outcome(project, "42", "pending")
    second = mark_outcome(project, "42", "acquiring")
    assert second.attempt_id is not None and second.attempt_id != first.attempt_id


def test_concurrent_browser_claims_cannot_start_two_attempts(project_with_selection: Path) -> None:
    from tum_mcp.studocu.state import mark_outcome

    def claim() -> str:
        try:
            mark_outcome(project_with_selection, "42", "acquiring")
            return "claimed"
        except CampusError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(outcomes) == ["blocked", "claimed"]


def test_superseded_staged_file_cannot_replace_the_current_selection(
    project_with_selection: Path, tmp_path: Path
) -> None:
    from tum_mcp.studocu.state import mark_outcome

    project = project_with_selection
    file = tmp_path / "original.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with file.open("wb") as output:
        writer.write(output)
    older = stage(project, "42", file)
    mark_outcome(project, "42", "pending")
    writer.add_blank_page(width=200, height=200)
    with file.open("wb") as output:
        writer.write(output)
    newer = stage(project, "42", file)
    with pytest.raises(CampusError):
        import_staged(project, "42", older)
    assert load_queue(project).documents[0].staged_name == newer
    assert import_staged(project, "42", newer)["pages"] == 2


def test_reclassify_pending_and_imported_document_without_changing_its_identity(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    selection = tmp_path / "reclassify.json"
    item = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation"})
    )
    item.update({"group": "other", "document_type": "other"})
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", file))
    before = load_state(project)
    original = next(r for r in before.resources if r.resource.key == "studocu-42")
    item.update({"group": "summaries", "document_type": "summary"})
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    plan(project, selection)
    after = load_state(project)
    moved = next(r for r in after.resources if r.resource.key == "studocu-42")
    assert moved.path == "materials/studocu/summaries/material-studocu-42.pdf"
    assert moved.sha256 == original.sha256 and moved.resource.url == original.resource.url
    assert (project / moved.path).read_bytes() == file.read_bytes()
    assert not (project / original.path).exists()
    assert load_queue(project).documents[0].group == "summaries"
    item.update({"decision": "exclude", "reason": "Not useful after review"})
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    plan(project, selection)
    excluded = load_queue(project).documents[0]
    assert excluded.decision == "exclude" and excluded.state == "imported"
    assert (project / moved.path).read_bytes() == file.read_bytes()


def test_reclassify_preserves_local_edits_and_destination_conflicts(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", file))
    item = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation"})
    )
    item["group"] = "summaries"
    selection = tmp_path / "reclassify.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    target = project / "materials/studocu/summaries/material-studocu-42.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"personal file")
    before = (project / ".tum-mcp/state.json").read_bytes()
    with pytest.raises(CampusError):
        plan(project, selection)
    assert target.read_bytes() == b"personal file"
    assert (project / ".tum-mcp/state.json").read_bytes() == before
    target.unlink()
    old = project / "materials/studocu/exams/material-studocu-42.pdf"
    old.write_bytes(b"personal edit")
    with pytest.raises(CampusError):
        plan(project, selection)
    assert old.read_bytes() == b"personal edit"
    assert (project / ".tum-mcp/state.json").read_bytes() == before


def test_reclassify_rolls_back_when_queue_write_fails(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", file))
    item = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation"})
    )
    item["group"] = "summaries"
    selection = tmp_path / "reclassify.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    state_before = (project / ".tum-mcp/state.json").read_bytes()
    queue_before = (project / ".tum-mcp/studocu/queue.json").read_bytes()
    write = study_store.private_write

    def fail_queue(path: Path, data: bytes) -> None:
        if path.name == "queue.json":
            raise OSError("synthetic interruption")
        write(path, data)

    with monkeypatch.context() as context:
        context.setattr(study_store, "private_write", fail_queue)
        with pytest.raises(CampusError):
            plan(project, selection)
    assert (project / ".tum-mcp/state.json").read_bytes() == state_before
    assert (project / ".tum-mcp/studocu/queue.json").read_bytes() == queue_before
    assert (
        project / "materials/studocu/exams/material-studocu-42.pdf"
    ).read_bytes() == file.read_bytes()
    assert not (project / "materials/studocu/summaries/material-studocu-42.pdf").exists()


def test_reclassify_rolls_back_if_old_file_cannot_be_removed(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", file))
    item = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation"})
    )
    item["group"] = "summaries"
    selection = tmp_path / "reclassify.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    state_before = (project / ".tum-mcp/state.json").read_bytes()
    queue_before = (project / ".tum-mcp/studocu/queue.json").read_bytes()
    old = project / "materials/studocu/exams/material-studocu-42.pdf"
    unlink = Path.unlink

    def fail_old(path: Path, *args, **kwargs) -> None:
        if path == old:
            raise OSError("synthetic deletion failure")
        unlink(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "unlink", fail_old)
        with pytest.raises(CampusError):
            plan(project, selection)
    assert old.read_bytes() == file.read_bytes()
    assert (project / ".tum-mcp/state.json").read_bytes() == state_before
    assert (project / ".tum-mcp/studocu/queue.json").read_bytes() == queue_before
    assert not (project / "materials/studocu/summaries/material-studocu-42.pdf").exists()


def test_reclassify_preserves_changes_made_after_transaction_preflight(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", file))
    item = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    item["group"] = "summaries"
    selection = tmp_path / "reclassify.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}))
    state_before = (project / ".tum-mcp/state.json").read_bytes()
    queue_path = project / ".tum-mcp/studocu/queue.json"
    destination = project / "materials/studocu/summaries/material-studocu-42.pdf"
    write = study_store.private_write

    def concurrent_edit(path: Path, data: bytes) -> None:
        write(path, data)
        if path == destination:
            queue_path.write_bytes(b"external edit")

    with monkeypatch.context() as context:
        context.setattr(study_store, "private_write", concurrent_edit)
        with pytest.raises(CampusError):
            plan(project, selection)
    assert queue_path.read_bytes() == b"external edit"
    assert (project / ".tum-mcp/state.json").read_bytes() == state_before
    assert (
        project / "materials/studocu/exams/material-studocu-42.pdf"
    ).read_bytes() == file.read_bytes()
    assert not destination.exists()


def test_validation_timeout_preserves_staged_original_for_retry(
    project_with_selection: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.moodle.extract_worker import ExtractionLimit

    project = project_with_selection
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    with monkeypatch.context() as context:

        def timeout(_body: bytes) -> int:
            raise ExtractionLimit()

        context.setattr("tum_mcp.studocu.imports.validate_pdf", timeout)
        staged = stage(project, "42", file)
    pending = load_queue(project).documents[0]
    assert pending.state == "downloaded" and pending.validation == "pending"
    assert (project / ".tum-mcp/studocu/incoming" / staged).read_bytes() == file.read_bytes()
    assert import_staged(project, "42", staged)["pages"] == 1
    assert load_queue(project).documents[0].validation == "validated"


def test_legacy_unconfirmed_queue_requires_course_confirmation(
    project_with_selection: Path, tmp_path: Path
) -> None:
    from tum_mcp.studocu.state import request_browser_download

    project = project_with_selection
    record_courses([{"course_id": 123, "institution_id": 92, "name": "Another Course"}])
    with pytest.raises(CampusError, match="Confirm"):
        request_browser_download(project, "42")
    selection = tmp_path / "confirmed.json"
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    with pytest.raises(CampusError, match="Confirm"):
        plan(project, selection)
    selection.write_text(
        json.dumps({"course_id": "123", "confirmed_course": True, "documents": entries})
    )
    plan(project, selection)
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    assert plan(project, selection).confirmed_course
    assert request_browser_download(project, "42").state == "action_required"


def test_studocu_preserves_live_course_schema_and_binding(
    project_with_selection: Path, tmp_path: Path
) -> None:
    snapshot = json.loads((tmp_path / "snapshot.json").read_text())
    snapshot["schema_version"] = 2
    snapshot["course"]["bindings"].append(
        {"key": "live", "provider": "tum_live", "course_id": "17", "course_slug": "lecture"}
    )
    snapshot["coverage"].append({"binding": "live", "status": "partial", "checked_at": "today"})
    source = tmp_path / "live-snapshot.json"
    source.write_text(json.dumps(snapshot))
    project = tmp_path / "live-course"
    sync(project, source, course_input="Course")
    selection = tmp_path / "live-selection.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": []}))
    plan(project, selection)
    record_discovery(project, "123", [{"id": "42", "course_id": 123}])
    entry = (
        load_queue(project_with_selection)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    selection.write_text(json.dumps({"course_id": "123", "documents": [entry]}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "live-supplement.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", pdf))
    state = load_state(project)
    assert state.schema_version == 2
    assert {binding.provider for binding in state.course.bindings} == {
        "moodle",
        "tum_live",
        "studocu",
    }
    assert (
        next(item for item in state.course.bindings if item.provider == "tum_live").course_slug
        == "lecture"
    )


@pytest.mark.parametrize(
    "interrupt_at", ["studocu-42.json", "material-studocu-43.pdf", "state.json", "queue.json"]
)
def test_interrupted_refresh_of_canonical_alias_recovers(
    project_with_selection: Path, tmp_path: Path, interrupt_at: str
) -> None:
    project = project_with_selection
    old = duplicate_pair(project, tmp_path).read_bytes()
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    entries[0]["refresh"] = True
    selection = tmp_path / "resume-refresh.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "new-original.pdf"
    with pdf.open("wb") as output:
        writer.write(output)
    staged = stage(project, "42", pdf)
    child = """import os, sys
from pathlib import Path
from tum_mcp import study_store
from tum_mcp.studocu.imports import import_staged
write = study_store.private_write
def interrupt(path, data):
    write(path, data)
    if path.name == sys.argv[3]: os._exit(73)
study_store.private_write = interrupt
import_staged(Path(sys.argv[1]), "42", sys.argv[2])
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", child, str(project), staged, interrupt_at], check=False
    )
    assert result.returncode == 73
    import_staged(project, "42", staged)
    sources = {item.resource.key: item for item in load_state(project).resources}
    assert (project / sources["studocu-42"].path).read_bytes() == pdf.read_bytes()
    assert (project / sources["studocu-43"].path).read_bytes() == old
    assert not list((project / ".tum-mcp/studocu/promotions").glob("*.json"))


def test_interrupted_promotion_preserves_an_edited_orphan(
    project_with_selection: Path, tmp_path: Path
) -> None:
    project = project_with_selection
    duplicate_pair(project, tmp_path)
    entries = [
        item.model_dump(
            exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"}
        )
        for item in load_queue(project).documents
    ]
    entries[0]["group"] = "summaries"
    selection = tmp_path / "interrupted-edited.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": entries}))
    child = """import os, sys
from pathlib import Path
from tum_mcp import study_store
from tum_mcp.studocu.state import plan
write = study_store.private_write
def interrupt(path, data):
    write(path, data)
    if path.name == "state.json": os._exit(73)
study_store.private_write = interrupt
plan(Path(sys.argv[1]), Path(sys.argv[2]))
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", child, str(project), str(selection)], check=False
    )
    assert result.returncode == 73
    orphan = project / "materials/studocu/exams/material-studocu-42.pdf"
    orphan.write_bytes(b"user edit")
    with pytest.raises(CampusError, match="recovery needs review"):
        plan(project, selection)
    assert orphan.read_bytes() == b"user edit"
    assert (project / ".tum-mcp/studocu/promotions/studocu-42.json").is_file()
