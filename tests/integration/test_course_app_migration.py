import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.study_build import build, read_content, unit_revision
from tum_mcp.study_store import END, START, digest, load_state


def tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


@pytest.fixture(autouse=True)
def legacy_inventory(project: Path) -> None:
    agents = project / "AGENTS.md"
    text = agents.read_text().replace("| `app/` |", "| `study/` |")
    agents.write_text(text)
    path = project / ".tum-mcp/state.json"
    state = json.loads(path.read_bytes())
    block = text[text.index(START) : text.index(END) + len(END)]
    state["agents_block_sha256"] = digest(block.encode())
    path.write_text(json.dumps(state))


def test_explicit_upgrade_preserves_identity_backup_and_user_files(project: Path) -> None:
    (project / "study/personal.txt").write_text("My notes")
    (project / ".tum-mcp/comments.json").write_text("private comments")
    original = tree(project / "study")
    state = load_state(project)
    revisions = [unit_revision(unit) for unit in read_content(project).units]
    result = CliRunner().invoke(
        app, ["study", "build", str(project), "--local-only", "--upgrade-layout"]
    )
    assert result.exit_code == 0, result.output
    assert not (project / "study").exists()
    assert tree(project / ".tum-mcp/layout-backup") == original
    assert (project / "app/personal.txt").read_text() == "My notes"
    assert (project / ".tum-mcp/comments.json").read_text() == "private comments"
    assert load_state(project).course == state.course
    assert [unit_revision(unit) for unit in read_content(project).units] == revisions
    assert "`app/`" in (project / "AGENTS.md").read_text()
    after = tree(project / "app")
    build(project, publish=False, upgrade_layout=True)
    assert tree(project / "app") == after


@pytest.mark.parametrize("conflict", ["styles.css", "data.mjs", "backup", "agents"])
def test_upgrade_conflicts_preserve_original(project: Path, conflict: str) -> None:
    if conflict == "backup":
        (project / ".tum-mcp/layout-backup").mkdir()
    elif conflict == "agents":
        path = project / "AGENTS.md"
        path.write_text(path.read_text().replace("## TUM MCP course project", "## My inventory"))
    else:
        (project / "study" / conflict).write_text("customized")
    before = tree(project)
    with pytest.raises(CampusError):
        build(project, publish=False, upgrade_layout=True)
    assert tree(project) == before


def test_interrupted_upgrade_restores_original(project: Path, monkeypatch) -> None:
    original = tree(project)
    rename = Path.rename

    def fail_destination(self: Path, destination: Path):
        if destination == project / "app":
            raise PermissionError("synthetic denied write")
        return rename(self, destination)

    monkeypatch.setattr(Path, "rename", fail_destination)
    with pytest.raises(CampusError, match="restored"):
        build(project, publish=False, upgrade_layout=True)
    assert tree(project) == original


def test_inventory_write_failure_restores_layout_and_instructions(
    project: Path, monkeypatch
) -> None:
    import tum_mcp.study_store as store

    original = tree(project)
    write = store.private_write

    def fail_state(path: Path, data: bytes):
        if path == project / ".tum-mcp/state.json":
            raise PermissionError("synthetic state write failure")
        return write(path, data)

    monkeypatch.setattr(store, "private_write", fail_state)
    with pytest.raises(CampusError, match="restored"):
        build(project, publish=False, upgrade_layout=True)
    assert tree(project) == original
