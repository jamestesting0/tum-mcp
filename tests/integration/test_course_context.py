import json
from pathlib import Path

import pytest
import yaml

from tum_mcp.course_context import context_review, context_status
from tum_mcp.errors import CampusError
from tum_mcp.study_store import load_state, upgrade_private
from tum_mcp.study_sync import sync


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


def test_explicit_private_upgrade_preserves_all_records_and_root_rules(project: Path) -> None:
    before_state = load_state(project)
    (project / ".tum-mcp/notes").mkdir()
    (project / ".tum-mcp/notes/course-rules.md").write_text("Cited bonus rule")
    (project / ".tum-mcp/github.json").write_text("private publication config")
    agents = project / "AGENTS.md"
    agents.write_text("User rules remain here.\n" + agents.read_text())
    original_agents = agents.read_bytes()
    original = {
        p.relative_to(project / ".tum-mcp"): p.read_bytes()
        for p in (project / ".tum-mcp").rglob("*")
        if p.is_file()
    }
    (project / ".tum-mcp").rename(project / ".study")
    assert load_state(project).course == before_state.course
    upgrade_private(project)
    assert not (project / ".study").exists()
    assert load_state(project).course == before_state.course
    assert load_state(project).generation == before_state.generation
    assert (project / ".tum-mcp/legacy-AGENTS.md").read_bytes() == original_agents
    assert agents.read_text().startswith("User rules remain here.")
    for relative, data in original.items():
        if relative.name != "state.json":
            assert (project / ".tum-mcp" / relative).read_bytes() == data
    upgrade_private(project)


def test_private_upgrade_refuses_two_folders_and_rolls_back_write_failure(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tum_mcp.study_store as store

    (project / ".tum-mcp").rename(project / ".study")
    (project / ".tum-mcp").mkdir()
    with pytest.raises(CampusError, match="Both"):
        upgrade_private(project)
    (project / ".tum-mcp").rmdir()
    original = (project / ".study/state.json").read_bytes()
    agents = (project / "AGENTS.md").read_bytes()
    write = store.private_write

    def fail(path, data):
        if path == project / ".tum-mcp/legacy-AGENTS.md":
            raise PermissionError("synthetic failure")
        return write(path, data)

    monkeypatch.setattr(store, "private_write", fail)
    with pytest.raises(CampusError, match="restored"):
        upgrade_private(project)
    assert (project / ".study/state.json").read_bytes() == original
    assert (project / "AGENTS.md").read_bytes() == agents
    assert not (project / ".tum-mcp").exists()


def test_upgrade_cutover_blocks_writers_without_open_file_handles(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from filelock import FileLock

    from tum_mcp.study_store import private_path

    (project / ".tum-mcp").rename(project / ".study")
    rename = Path.rename

    def cutover(path: Path, destination: Path):
        if path == project / ".study":
            assert (path / "migration.lock").exists()
            with pytest.raises(CampusError, match="migration"):
                private_path(project, "state.json")
            for name in ("publish", "update", "comments"):
                # Models the Windows requirement: rename cannot hold file handles.
                with FileLock(str(path / f"{name}.lock"), timeout=0):
                    pass
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", cutover)
    upgrade_private(project)
    assert not (project / ".tum-mcp/migration.lock").exists()
    assert load_state(project).course.key
