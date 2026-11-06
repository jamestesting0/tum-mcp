import json
from pathlib import Path

import pytest
import yaml

from tum_mcp.course.project.context import context_review, context_status
from tum_mcp.course.project.store import (
    load_state,
)
from tum_mcp.course.project.sync import sync


def test_handbook_is_preserved_and_review_receipt_identifies_changed_support(
    project: Path, inputs: Path
) -> None:
    state = load_state(project)
    path = project / ".tum-mcp/course.md"
    assert context_status(project, state) == "unreviewed"
    header = {
        "course_key": state.course.key,
        "semester": state.course.semester,
        "reviewed_generation": state.generation,
        "reviewed_sources": {state.resources[0].resource.key: state.resources[0].sha256},
    }
    text = "---\n" + yaml.safe_dump(header) + "---\n# Course\nMy cited orientation and unknowns.\n"
    path.write_text(text)
    assert context_status(project, state) == "current"
    source = project / state.resources[0].path
    original_source = source.read_bytes()
    source.write_bytes(original_source + b"local edit")
    assert context_status(project, state) == "stale"
    source.write_bytes(original_source)
    payload = json.loads(inputs.read_bytes())
    changed = next(
        item for item in payload["resources"] if item["key"] == state.resources[0].resource.key
    )
    changed["text"] += "\nChanged organization rule."
    changed["revision"] = "changed-rule"
    inputs.write_text(json.dumps(payload))
    sync(project, inputs)
    assert path.read_text() == text
    review = context_review(project, load_state(project))
    assert review.status == "stale"
    assert state.resources[0].resource.key in review.changed_sources


@pytest.mark.parametrize("header", ["course_key: wrong\nsemester: WS26\n", "bad: [", "[]"])
def test_foreign_or_invalid_handbook_cannot_claim_review(project: Path, header: str) -> None:
    (project / ".tum-mcp/course.md").write_text("---\n" + header + "\n---\nNotes")
    assert context_status(project, load_state(project)) == "invalid"
