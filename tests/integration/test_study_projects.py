import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_build import build, read_content, stale_units
from tum_mcp.study_store import load_state
from tum_mcp.study_sync import sync


def test_initialization_requires_an_explicit_course_before_creating_files(
    tmp_path: Path, inputs: Path
) -> None:
    root = tmp_path / "new"
    result = CliRunner().invoke(app, ["study", "init", str(root), "--snapshot", str(inputs)])
    assert result.exit_code == 2
    assert not root.exists()


def test_one_project_cannot_change_course_identity(project: Path, inputs: Path) -> None:
    before = (project / ".study/state.json").read_bytes()
    incoming = json.loads(inputs.read_bytes())
    incoming["course"]["key"] = "another-course"
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    with pytest.raises(CampusError) as error:
        sync(project, inputs)
    assert error.value.code == Code.SCOPE_DENIED
    assert (project / ".study/state.json").read_bytes() == before


def test_source_update_invalidates_only_dependent_units(project: Path, inputs: Path) -> None:
    incoming = json.loads(inputs.read_bytes())
    incoming["resources"][1]["text"] += "\nVerified source revision two.\n"
    incoming["resources"][1]["revision"] = "2"
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    sync(project, inputs)
    assert stale_units(project, load_state(project), read_content(project)) == ("bfs",)
    previous_site = (project / "study/data.mjs").read_bytes()
    with pytest.raises(CampusError) as error:
        build(project)
    assert error.value.code == Code.STALE_RESULT
    assert (project / "study/data.mjs").read_bytes() == previous_site


@pytest.mark.parametrize("deleted", [False, True])
def test_update_preserves_and_reports_local_material_edits(
    project: Path, inputs: Path, deleted: bool
) -> None:
    target = project / "materials/content/material-bfs.md"
    if deleted:
        target.unlink()
    else:
        target.write_bytes(b"local study annotation")
    report = sync(project, inputs)
    assert report.conflicts == ("bfs",)
    assert not target.exists() if deleted else target.read_bytes() == b"local study annotation"
    assert (
        next(r for r in load_state(project).resources if r.resource.key == "bfs").status
        == "local_edit"
    )


@pytest.mark.parametrize("coverage,expected", [("partial", "current"), ("complete", "withdrawn")])
def test_missing_sources_are_withdrawn_only_after_complete_coverage(
    project: Path, inputs: Path, coverage: str, expected: str
) -> None:
    incoming = json.loads(inputs.read_bytes())
    incoming["resources"] = [r for r in incoming["resources"] if r["key"] != "bfs"]
    incoming["coverage"][0]["status"] = coverage
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    original = (project / "materials/content/material-bfs.md").read_bytes()
    sync(project, inputs)
    stored = next(r for r in load_state(project).resources if r.resource.key == "bfs")
    assert stored.status == expected
    assert (project / stored.path).read_bytes() == original


def test_metadata_without_reliable_revision_does_not_claim_payload_freshness(
    project: Path, inputs: Path
) -> None:
    incoming = json.loads(inputs.read_bytes())
    incoming["resources"][0].pop("text")
    incoming["resources"][0].pop("revision")
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    sync(project, inputs)
    assert (
        next(r for r in load_state(project).resources if r.resource.key == "graphs").status
        == "needs_fetch"
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_custom_course_instructions_and_extra_files_survive_updates(
    project: Path, inputs: Path, newline: str
) -> None:
    agents = project / "AGENTS.md"
    prefix = ("# My course rules" + newline * 2).encode()
    suffix = (newline + "Personal rule to keep." + newline).encode()
    block = agents.read_text(encoding="utf-8").replace("\n", newline).encode()
    agents.write_bytes(prefix + block + suffix)
    note = project / "materials/content/personal-note.md"
    note.write_bytes(b"personal notes")
    sync(project, inputs)
    sync(project, inputs)  # The stored digest must remain valid after another update.
    current = agents.read_bytes()
    assert current.startswith(prefix) and current.endswith(suffix)
    if newline == "\r\n":
        assert b"\n" not in current.replace(b"\r\n", b"")
    assert note.read_bytes() == b"personal notes"


def test_edited_inventory_block_stops_update_before_any_file_is_replaced(
    project: Path, inputs: Path
) -> None:
    agents = project / "AGENTS.md"
    agents.write_bytes(
        agents.read_bytes().replace(b"Course study inventory", b"My edited inventory")
    )
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    incoming = json.loads(inputs.read_bytes())
    incoming["resources"][0]["text"] += "\nNew source text."
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    with pytest.raises(CampusError) as error:
        sync(project, inputs)
    assert error.value.code == Code.WORKSPACE_CONFLICT
    assert {
        p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()
    } == before


def test_imports_cannot_escape_the_snapshot_directory(tmp_path: Path, inputs: Path) -> None:
    incoming = json.loads(inputs.read_bytes())
    incoming["resources"][0].pop("text")
    incoming["resources"][0]["source_file"] = "../private.txt"
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    with pytest.raises(CampusError) as error:
        sync(tmp_path / "new", inputs, course_input="Algorithms & Graphs")
    assert error.value.code == Code.INVALID_RESPONSE
    assert not (tmp_path / "new").exists()


def test_edited_renderer_is_retained_when_data_is_rebuilt(project: Path) -> None:
    target = project / "study/styles.css"
    custom = target.read_bytes() + b"\n/* user theme */\n"
    target.write_bytes(custom)
    report = build(project)
    assert report.preserved_templates == ("styles.css",)
    assert target.read_bytes() == custom


def test_interrupted_write_restores_the_previous_project(
    project: Path, inputs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    incoming = json.loads(inputs.read_bytes())
    incoming["resources"][0]["text"] += "\nA source change."
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    write = study_store.private_write
    failed = False

    def fail_once(path: Path, data: bytes) -> None:
        nonlocal failed
        if path.name == "state.json" and not failed:
            failed = True
            raise PermissionError("synthetic interruption")
        write(path, data)

    monkeypatch.setattr(study_store, "private_write", fail_once)
    with pytest.raises(CampusError) as error:
        sync(project, inputs)
    assert error.value.code == Code.WORKSPACE_CONFLICT
    assert failed
    assert {
        p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()
    } == before


def test_adding_a_verified_source_binding_preserves_course_progress_namespace(project, inputs):
    before = (project / "study/data.mjs").read_text(encoding="utf-8")
    previous = json.loads(before.removeprefix("export default ").removesuffix(";\n"))
    incoming = json.loads(inputs.read_bytes())
    # Synthetic sources remain synthetic; a new source mapping must not change course identity.
    incoming["course"]["bindings"].append(
        {"key": "extra", "provider": "sample", "course_id": "extra"}
    )
    incoming["coverage"].append(
        {"binding": "extra", "status": "partial", "checked_at": "2026-10-25"}
    )
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    sync(project, inputs)
    build(project)
    current = json.loads(
        (project / "study/data.mjs")
        .read_text(encoding="utf-8")
        .removeprefix("export default ")
        .removesuffix(";\n")
    )
    assert current["course"]["identity"] == previous["course"]["identity"]
    assert [u["revision"] for u in current["units"]] == [u["revision"] for u in previous["units"]]


def test_repeated_pending_metadata_never_promotes_old_content_to_current(
    project: Path, inputs: Path
) -> None:
    incoming = json.loads(inputs.read_bytes())
    source = next(r for r in incoming["resources"] if r["key"] == "bfs")
    old_payload = source.pop("text")
    source["revision"] = "new-unfetched-version"
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    for _ in range(2):
        sync(project, inputs)
        item = next(r for r in load_state(project).resources if r.resource.key == "bfs")
        assert item.status == "needs_fetch"
        with pytest.raises(CampusError) as error:
            build(project)
        assert error.value.code == Code.STALE_RESULT
    source["text"] = old_payload + "\nVerified new source content.\n"
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    sync(project, inputs)
    assert (
        next(r for r in load_state(project).resources if r.resource.key == "bfs").status
        == "current"
    )
    assert stale_units(project, load_state(project), read_content(project)) == ("bfs",)


@pytest.mark.parametrize("identity_change", ["url", "binding", "locator"])
def test_equal_revision_on_another_source_does_not_reuse_old_payload(
    project: Path, inputs: Path, identity_change: str
) -> None:
    incoming = json.loads(inputs.read_bytes())
    source = next(r for r in incoming["resources"] if r["key"] == "bfs")
    source.pop("text")
    if identity_change == "url":
        source["url"] += "?edition=another-source"
    elif identity_change == "locator":
        source["locator"] = "Another passage, pages 20–24"
    else:
        incoming["course"]["bindings"].append(
            {"key": "another", "provider": "sample", "course_id": "another"}
        )
        incoming["coverage"].append(
            {"binding": "another", "status": "partial", "checked_at": "2026-10-25"}
        )
        source["binding"] = "another"
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    sync(project, inputs)
    item = next(r for r in load_state(project).resources if r.resource.key == "bfs")
    assert item.status == "needs_fetch"
    with pytest.raises(CampusError) as error:
        build(project)
    assert error.value.code == Code.STALE_RESULT


def test_complete_inventory_reuses_unchanged_payloads_without_withdrawing_them(
    project: Path, inputs: Path
) -> None:
    incoming = json.loads(inputs.read_bytes())
    original = load_state(project)
    for source in incoming["resources"]:
        source.pop("text", None)
    incoming["coverage"][0]["status"] = "complete"
    inputs.write_text(json.dumps(incoming), encoding="utf-8")
    report = sync(project, inputs)
    current = load_state(project)
    assert report.imported == 0 and report.withdrawn == 0 and report.conflicts == ()
    assert len(current.resources) == len(original.resources)
    assert all(r.status == "current" for r in current.resources)
    assert [r.sha256 for r in current.resources] == [r.sha256 for r in original.resources]
    assert stale_units(project, current, read_content(project)) == ()
