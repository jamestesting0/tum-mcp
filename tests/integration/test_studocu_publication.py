import io
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from tum_mcp.errors import CampusError, Code
from tum_mcp.studocu.courses import record_courses
from tum_mcp.studocu.imports import import_staged, stage
from tum_mcp.studocu.state import plan, record_discovery
from tum_mcp.study_build import build
from tum_mcp.study_publish import configure
from tum_mcp.study_publish_site import export_site
from tum_mcp.study_store import load_state


@pytest.fixture
def supplemented_project(project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    record_courses([{"course_id": 123, "institution_id": 92, "name": "Algorithms & Graphs"}])
    state_path = project / ".tum-mcp/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["course"]["synthetic"] = False
    for binding in state["course"]["bindings"]:
        binding["provider"] = "moodle"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": []}), encoding="utf-8")
    plan(project, selection)
    record_discovery(project, "123", [{"id": "42", "course_id": 123}])
    selection.write_text(
        json.dumps(
            {
                "course_id": "123",
                "documents": [
                    {
                        "document_id": "42",
                        "decision": "include",
                        "reason": "Relevant mock examination",
                        "title": "Student mock",
                        "url": "https://www.studocu.com/de/document/42",
                        "group": "exams",
                        "document_type": "mock",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    original = tmp_path / "original.pdf"
    original.write_bytes(output.getvalue())
    import_staged(project, "42", stage(project, "42", original))
    build(project, publish=False)
    return project


def test_unrelated_private_source_does_not_block_export(supplemented_project: Path) -> None:
    assert b"data.hosted = true" in export_site(supplemented_project)["data.mjs"]


def test_changed_unreferenced_private_source_does_not_stale_official_export(
    supplemented_project: Path, tmp_path: Path
) -> None:
    from tum_mcp.studocu.state import load_queue

    project = supplemented_project
    item = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    item["refresh"] = True
    selection = tmp_path / "refresh.json"
    selection.write_text(json.dumps({"course_id": "123", "documents": [item]}), encoding="utf-8")
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    file = tmp_path / "new-original.pdf"
    with file.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", file))
    site = export_site(project)
    assert b"data.hosted = true" in site["data.mjs"]
    assert b"studocu-42" not in site["data.mjs"]


def test_included_private_source_blocks_before_github(
    supplemented_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = supplemented_project
    source = next(r for r in load_state(project).resources if r.resource.key == "studocu-42")
    path = project / "study/content.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    content["units"][0]["sources"].append({"key": source.resource.key, "sha256": source.sha256})
    path.write_text(json.dumps(content), encoding="utf-8")
    build(project, publish=False)
    monkeypatch.setattr(
        "tum_mcp.study_publish.GitHub.discover", lambda: pytest.fail("GitHub was contacted")
    )
    with pytest.raises(CampusError) as error:
        configure(project)
    assert error.value.code == Code.SCOPE_DENIED
    assert "studocu-42" in error.value.message


def test_edited_generated_fields_cannot_enter_public_export(supplemented_project: Path) -> None:
    project = supplemented_project
    generated = project / "study/data.mjs"
    text = generated.read_text(encoding="utf-8")
    payload = json.loads(text.removeprefix("export default ").removesuffix(";\n"))
    payload["inlineMath"]["injected"] = "synthetic private text"
    generated.write_text("export default " + json.dumps(payload) + ";\n", encoding="utf-8")
    with pytest.raises(CampusError):
        export_site(project)


def test_studocu_source_cannot_be_downgraded_to_a_campus_binding(
    supplemented_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = supplemented_project / ".tum-mcp/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    source = next(item for item in state["resources"] if item["resource"]["key"] == "studocu-42")
    source["resource"]["binding"] = next(
        item["key"] for item in state["course"]["bindings"] if item["provider"] == "moodle"
    )
    original = (supplemented_project / source["path"]).read_bytes()
    source["resource"].pop("studocu")
    source["path"] = "materials/exams/material-studocu-42.pdf"
    (supplemented_project / source["path"]).write_bytes(original)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    content_path = supplemented_project / "study/content.json"
    content = json.loads(content_path.read_text(encoding="utf-8"))
    content["units"][0]["sources"].append({"key": "studocu-42", "sha256": source["sha256"]})
    content_path.write_text(json.dumps(content), encoding="utf-8")
    build(supplemented_project, publish=False)
    monkeypatch.setattr(
        "tum_mcp.study_publish.GitHub.discover", lambda: pytest.fail("GitHub was contacted")
    )
    with pytest.raises(CampusError) as error:
        configure(supplemented_project)
    assert error.value.code == Code.SCOPE_DENIED


def test_legacy_studocu_link_stays_readable_but_cannot_be_published(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = project / ".tum-mcp/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    source = next(item for item in state["resources"] if item["resource"]["key"] == "graphs")
    source["resource"]["url"] = "https://www.studocu.com/de/document/42"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert load_state(project).course.synthetic
    build(project, publish=False)
    monkeypatch.setattr(
        "tum_mcp.study_publish.GitHub.discover", lambda: pytest.fail("GitHub was contacted")
    )
    with pytest.raises(CampusError) as error:
        configure(project)
    assert error.value.code == Code.SCOPE_DENIED


def test_excluded_private_exercises_do_not_block_official_study_export(
    supplemented_project: Path, exercise_project: Path, tmp_path: Path
) -> None:
    from tum_mcp.studocu.state import load_queue

    project = supplemented_project
    source = next(
        item for item in load_state(project).resources if item.resource.key == "studocu-42"
    )
    data = json.loads((exercise_project / "study/exercises.json").read_text(encoding="utf-8"))
    exercise = data["sets"][0]["exercises"][0]
    old_key = exercise["sources"][0]["key"]

    def replace(value):
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == "sources":
                    result[key] = [
                        "studocu-42" if entry == old_key else replace(entry) for entry in item
                    ]
                else:
                    result[key] = replace(item)
            return result
        return value

    updated = replace(exercise)
    updated["sources"][0]["key"] = "studocu-42"
    updated["sources"][0]["sha256"] = source.sha256
    data["sets"][0]["exercises"][0] = updated
    (project / "study/exercises.json").write_text(json.dumps(data), encoding="utf-8")
    build(project, publish=False)
    assert b"data.hosted = true" in export_site(project, include_exercises=False)["data.mjs"]
    with pytest.raises(CampusError) as error:
        export_site(project, include_exercises=True)
    assert error.value.code == Code.SCOPE_DENIED
    selected = (
        load_queue(project)
        .documents[0]
        .model_dump(exclude={"state", "duplicate_of", "staged_name", "validation", "attempt_id"})
    )
    selected["refresh"] = True
    selection = tmp_path / "refresh-exercise.json"
    selection.write_text(
        json.dumps({"course_id": "123", "documents": [selected]}), encoding="utf-8"
    )
    plan(project, selection)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    newer = tmp_path / "new-exercise-source.pdf"
    with newer.open("wb") as output:
        writer.write(output)
    import_staged(project, "42", stage(project, "42", newer))
    assert b"data.hosted = true" in export_site(project, include_exercises=False)["data.mjs"]
    with pytest.raises(CampusError):
        export_site(project, include_exercises=True)
    from tum_mcp.study_publish import build_for_publication, publish
    from tum_mcp.study_publish_models import Publication, course_identity, save_publication
    from tum_mcp.study_publish_site import site_digest

    build_for_publication(project, include_exercises=False)
    site = export_site(project)
    commit = "a" * 40
    save_publication(
        project,
        Publication(
            course_identity=course_identity(load_state(project).course),
            repository="example/course",
            public_site=True,
            branch="main",
            commit=commit,
            deployed_commit=commit,
            site_digest=site_digest(site),
        ),
    )
    assert publish(project).status == "unchanged"
