import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.errors import CampusError
from tum_mcp.study_models import Resource, Snapshot, material_path
from tum_mcp.study_store import load_state
from tum_mcp.study_sync import sync


def studocu_resource(group: str = "summaries") -> dict:
    return {
        "key": "studocu-42",
        "binding": "studocu",
        "kind": "content",
        "title": "Student summary",
        "url": "https://www.studocu.com/de/document/42",
        "studocu": {"document_id": "42", "course_id": "123", "storage_group": group},
    }


@pytest.mark.parametrize("group", ["summaries", "exams", "other"])
def test_storage_groups(group: str) -> None:
    resource = Resource.model_validate(studocu_resource(group))
    assert material_path(resource, ".pdf") == f"materials/studocu/{group}/material-studocu-42.pdf"


def test_retained_binding_preserves_metadata_without_revision(tmp_path: Path) -> None:
    project = tmp_path / "course"
    incoming = tmp_path / "snapshot.json"
    snapshot = {
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
                "text": "Original text",
            }
        ],
    }
    incoming.write_text(json.dumps(snapshot))
    sync(project, incoming, course_input="Course")
    original = load_state(project)
    snapshot["course"]["bindings"].append(
        {"key": "studocu", "provider": "studocu", "course_id": "123"}
    )
    snapshot["coverage"] = [{"binding": "studocu", "status": "partial", "checked_at": "later"}]
    snapshot["resources"] = [studocu_resource()]
    snapshot["retained_bindings"] = ["moodle"]
    incoming.write_text(json.dumps(snapshot))
    sync(project, incoming)
    updated = load_state(project)
    assert (
        next(r for r in updated.resources if r.resource.key == "lecture") == original.resources[0]
    )
    assert next(c for c in updated.coverage if c.binding == "moodle") == original.coverage[0]
    assert (project / "materials/content/material-lecture.md").read_text() == "Original text"


def test_retained_payload_and_invalid_provenance_are_rejected(tmp_path: Path) -> None:
    course = {
        "key": "course",
        "title": "Course",
        "semester": "Winter",
        "bindings": [{"key": "studocu", "provider": "studocu", "course_id": "123"}],
    }
    resource = studocu_resource()
    with pytest.raises(ValidationError):
        Snapshot.model_validate(
            {
                "course": course,
                "coverage": [],
                "resources": [resource],
                "retained_bindings": ["studocu"],
            }
        )
    resource["studocu"]["course_id"] = "999"
    with pytest.raises(ValidationError):
        Snapshot.model_validate(
            {
                "course": course,
                "coverage": [{"binding": "studocu", "status": "partial", "checked_at": "now"}],
                "resources": [resource],
            }
        )
    resource["studocu"]["course_id"] = "123"
    incoming = tmp_path / "snapshot.json"
    incoming.write_text(
        json.dumps(
            {"course": course, "coverage": [], "resources": [], "retained_bindings": ["studocu"]}
        )
    )
    with pytest.raises(CampusError):
        sync(tmp_path / "new", incoming, course_input="Course")


def test_studocu_only_course_can_be_initialized_without_campus_accounts(tmp_path: Path) -> None:
    incoming = tmp_path / "snapshot.json"
    incoming.write_text(
        json.dumps(
            {
                "course": {
                    "key": "course",
                    "title": "Course",
                    "semester": "Winter",
                    "bindings": [{"key": "studocu", "provider": "studocu", "course_id": "123"}],
                },
                "coverage": [{"binding": "studocu", "status": "partial", "checked_at": "now"}],
                "resources": [],
            }
        )
    )
    project = tmp_path / "new"
    sync(project, incoming, course_input="Course")
    assert load_state(project).course.bindings[0].provider == "studocu"
