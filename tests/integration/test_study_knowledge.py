"""Course links must preserve source, layout and read-only boundaries."""

import os
from pathlib import Path

import pytest
from documents import content_file
from knowledge_fixture import knowledge_project

from tum_mcp.course.app.build import read_content, stale_units
from tum_mcp.course.content.exam_data import read_exam
from tum_mcp.course.content.exercise_data import read_exercises
from tum_mcp.course.lecture.data import read_lectures, stale_lectures
from tum_mcp.course.memory.projection import project
from tum_mcp.course.memory.store import read_inputs
from tum_mcp.course.project.paths import app_path
from tum_mcp.course.project.store import load_state
from tum_mcp.errors import CampusError

pytestmark = pytest.mark.usefixtures("lecture_extension")


@pytest.mark.parametrize("layout", [("app", ".tum-mcp")])
def test_fixture_preserves_source_scope_and_both_layouts(tmp_path: Path, layout) -> None:
    root = knowledge_project(tmp_path, layout)
    state = load_state(root)
    assert len(read_content(root).units) == 2
    assert len(read_exercises(root).sets) == 1
    assert read_exam(root).sittings
    assert stale_units(root, state, read_content(root)) == ()
    assert stale_lectures(root, state, read_lectures(root)) == ()
    assert not (root / layout[1] / "knowledge.json").exists()


def test_fixture_exercises_can_exist_before_study(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path, workspaces=frozenset({"exercises"}))
    assert read_exercises(root).sets[0].exercises[0].prerequisites == ()
    assert not content_file(root, "study").exists()


def test_malformed_content_preserves_bytes(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    path = app_path(root, "study/course.json")
    path.write_text('{"PRIVATE_SENTINEL":', encoding="utf-8")
    with pytest.raises(CampusError):
        read_content(root)
    assert path.read_text(encoding="utf-8") == '{"PRIVATE_SENTINEL":'


def test_projection_preserves_native_direction_roles_and_workspace_identity(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    graph = project(read_inputs(root))
    assert {node.workspace for node in graph.nodes.values()} >= {
        "study",
        "exercises",
        "exam",
        "lectures",
    }
    assert any(
        e.start == "study/unit/observer/block/observer-definition"
        and e.end == "exercises/set/sheet-1/exercise/observer-practice"
        and e.relation == "prerequisite_of"
        for e in graph.edges
    )
    assert all("SOLUTION_SECRET" not in n.title + n.summary + n.body for n in graph.nodes.values())
    for link in graph.inputs.exam.links:
        assert any(
            e.start == f"exam/concept/{link.start}" and e.end == f"exam/concept/{link.end}"
            for e in graph.edges
        )
    assert graph.nodes["study/unit/observer/explore/observer-extra"].scope["role"] == "enrichment"
    assert any(node.scope.get("origin") == "synthetic" for node in graph.nodes.values())
    assert any(node.scope.get("relevance") == "outdated" for node in graph.nodes.values())
    assert not graph.issues


def test_cli_context_and_impact_need_no_extension(tmp_path: Path) -> None:
    import json

    from typer.testing import CliRunner

    from tum_mcp.cli import app

    root = knowledge_project(tmp_path)
    assert not (Path(os.environ["TUM_MCP_CONFIG_DIR"]) / "extensions.json").exists()
    runner = CliRunner()
    for args in (
        ["context", str(root), "Observer", "--max-bytes", "2048"],
        ["impact", str(root), "--source", "slides"],
    ):
        result = runner.invoke(app, ["study", *args])
        assert result.exit_code == 0, (result.output, result.exception)
        assert json.loads(result.output)
        if args[0] == "context":
            assert len(result.output.encode()) <= 2048
    result = runner.invoke(app, ["study", "report", str(root), "--json"])
    assert result.exit_code == 0, (result.output, result.exception)
    assert set(json.loads(result.output)) == {
        "quality",
        "structure",
        "coverage",
        "review",
        "render",
    }


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["Observer", "--item", "study/unit/observer"],
        ["Observer", "--purpose", "bogus"],
        ["Observer", "--limit", "0"],
    ],
)
def test_cli_invalid_context_does_not_write(tmp_path: Path, args) -> None:
    from typer.testing import CliRunner

    from tum_mcp.cli import app

    root = knowledge_project(tmp_path)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = CliRunner().invoke(app, ["study", "context", str(root), *args])
    assert result.exit_code != 0
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_retained_registry_file_is_ignored(tmp_path: Path) -> None:
    from tum_mcp.course.memory.query import context
    from tum_mcp.course.project.store import private_path

    root = knowledge_project(tmp_path)
    before = context(root, item="exercises/set/sheet-1/exercise/observer-practice", limit=4)
    private_path(root, "knowledge.json").write_text('{"PRIVATE_SENTINEL":')
    after = context(root, item="exercises/set/sheet-1/exercise/observer-practice", limit=4)
    before.pop("snapshot_digest")
    after.pop("snapshot_digest")
    assert after == before


def test_unknown_link_decision_fields_never_echo_private_field_names(tmp_path: Path) -> None:
    import json

    from typer.testing import CliRunner

    from tum_mcp.cli import app
    from tum_mcp.course.project.store import private_path

    root = knowledge_project(tmp_path)
    path = private_path(root, "links.json")
    value = json.loads(path.read_bytes()) if path.exists() else {"schema_version": 1}
    value["PRIVATE_FIELD_SENTINEL"] = "PRIVATE_VALUE_SENTINEL"
    path.write_text(json.dumps(value))
    result = CliRunner().invoke(app, ["study", "context", str(root), "Observer"])
    assert result.exit_code != 0 and isinstance(result.exception, CampusError)
    assert "PRIVATE" not in str(result.exception) + result.output
