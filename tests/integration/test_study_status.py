"""The unified workflow routes without writing or mistaking damaged state for setup."""

import json
from pathlib import Path
from typing import Literal, assert_never

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.study_status import project_status
from tum_mcp.study_store import START


def test_status_accepts_new_and_unmanaged_projects_without_creating_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    root = tmp_path / "new" / "nested"
    result = CliRunner().invoke(app, ["study", "status", str(root)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "initialize"
    assert not (tmp_path / "new").exists()
    assert not (tmp_path / "data").exists() and not (tmp_path / "config").exists()
    root.mkdir(parents=True)
    rules = root / "AGENTS.md"
    rules.write_text("Keep my handwritten learning notes.\n", encoding="utf-8")
    before = rules.stat().st_mtime_ns
    assert project_status(root).mode == "initialize"
    assert rules.stat().st_mtime_ns == before
    assert {p.name for p in root.iterdir()} == {"AGENTS.md"}


def test_existing_binding_routes_to_sync_even_when_the_optional_site_is_broken(
    project: Path,
) -> None:
    notes = project / "AGENTS.md"
    notes.write_text(notes.read_text(encoding="utf-8") + "\nPersonal rule to keep.\n")
    (project / "study/content.json").write_bytes(b"broken optional website input")
    material = project / "materials/content/material-bfs.md"
    material.write_bytes(b"My local annotation")
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    result = CliRunner().invoke(app, ["study", "status", str(project)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["mode"] == "sync"
    assert report["course"] == {
        "key": "algorithms-demo",
        "title": "Algorithms & Graphs",
        "semester": "Synthetic course",
        "synthetic": True,
    }
    assert report["resources"] > 0
    assert {
        p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize("existing", [".study", "materials", "study", "managed-rules"])
def test_orphaned_material_requires_inspection_before_adoption(
    tmp_path: Path, existing: str
) -> None:
    if existing == "managed-rules":
        (tmp_path / "AGENTS.md").write_text(START + "\nOld managed course.\n")
    else:
        (tmp_path / existing).mkdir()
        (tmp_path / existing / "note.txt").write_bytes(b"Retain this material")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert project_status(tmp_path).mode == "recover"
    assert {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize(
    "damage", ["invalid-json", "directory", "oversized", "duplicate", "unscoped"]
)
def test_damaged_state_never_routes_to_initialization(
    project: Path,
    damage: Literal["invalid-json", "directory", "oversized", "duplicate", "unscoped"],
) -> None:
    path = project / ".study/state.json"
    match damage:
        case "invalid-json":
            path.write_bytes(b'{"private-fixture": "do not print these bytes"')
        case "directory":
            path.unlink()
            path.mkdir()
        case "oversized":
            path.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
        case "duplicate" | "unscoped":
            state = json.loads(path.read_bytes())
            if damage == "duplicate":
                state["resources"].append(state["resources"][0])
            else:
                state["resources"][0]["resource"]["binding"] = "unknown-binding"
            path.write_text(json.dumps(state))
        case unreachable:
            assert_never(unreachable)
    before = path.read_bytes() if path.is_file() else None
    result = CliRunner().invoke(app, ["study", "status", str(project)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "recover"
    assert "private-fixture" not in result.output
    assert path.read_bytes() == before if before is not None else path.is_dir()


@pytest.mark.parametrize("damage", ["missing", "edited", "non-utf8"])
def test_managed_instruction_conflicts_keep_the_known_course(
    project: Path, damage: Literal["missing", "edited", "non-utf8"]
) -> None:
    path = project / "AGENTS.md"
    match damage:
        case "missing":
            path.unlink()
        case "edited":
            path.write_text(path.read_text().replace("Course study inventory", "My inventory"))
        case "non-utf8":
            path.write_bytes(b"\xff\xfe")
        case unreachable:
            assert_never(unreachable)
    status = project_status(project)
    assert status.mode == "recover" and status.reason == "managed_instructions_need_review"
    assert status.course is not None and status.course.key == "algorithms-demo"


def test_symbolic_state_is_preserved(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"Unrelated bytes")
    project = tmp_path / "course"
    (project / ".study").mkdir(parents=True)
    state = project / ".study/state.json"
    try:
        state.symlink_to(outside)
    except OSError:
        pytest.skip("Native symlink creation not available.")
    assert project_status(project).mode == "recover"
    assert state.is_symlink() and outside.read_bytes() == b"Unrelated bytes"


def test_occupied_project_and_parent_are_reported_read_only(tmp_path: Path) -> None:
    path = tmp_path / "occupied"
    path.write_bytes(b"Keep")
    assert project_status(path).reason == "project_path_occupied"
    assert project_status(path / "child").reason == "project_parent_occupied"
    assert path.read_bytes() == b"Keep"
