"""Knowledge operations must preserve source, layout and read-only boundaries."""

from pathlib import Path

import pytest
from knowledge_annotations import annotation, write_registry
from knowledge_fixture import knowledge_project

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError
from tum_mcp.exam_data import read_exam
from tum_mcp.exercise_data import read_exercises
from tum_mcp.lecture_data import read_lectures, stale_lectures
from tum_mcp.study_build import read_content, stale_units
from tum_mcp.study_knowledge_assertions import AssertionChecks
from tum_mcp.study_knowledge_evidence import EvidenceChecks
from tum_mcp.study_knowledge_projection import project
from tum_mcp.study_knowledge_store import load_inputs
from tum_mcp.study_store import load_state

pytestmark = pytest.mark.usefixtures("course_memory")


@pytest.mark.parametrize("layout", [("app", ".tum-mcp"), ("study", ".study")])
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
    assert not app_path(root, "content.json").exists()


def test_fixture_conflicting_layout_and_malformed_content_preserve_bytes(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    path = app_path(root, "content.json")
    path.write_text('{"PRIVATE_SENTINEL":', encoding="utf-8")
    with pytest.raises(CampusError):
        read_content(root)
    assert path.read_text(encoding="utf-8") == '{"PRIVATE_SENTINEL":'
    (root / "study").mkdir()
    with pytest.raises(CampusError, match="Both app/ and study/"):
        app_path(root, "content.json")


def test_projection_preserves_native_direction_roles_and_workspace_identity(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    graph = project(load_inputs(root))
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


def test_semantics_require_explicit_review_and_do_not_merge_native_concepts(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    write_registry(root, [annotation(root)])
    graph = project(load_inputs(root))
    checks = AssertionChecks(graph, EvidenceChecks(graph.inputs))
    assessment = checks.assertion("teaching")
    assert assessment.state == "candidate" and assessment.ready_for_review
    assert "concept/observer" in graph.nodes and "exam/concept/observer" in graph.nodes
    assert not any(e.origin == "reviewed" for e in graph.edges)
    write_registry(root, [annotation(root)], reviewed=True)
    graph = project(load_inputs(root))
    checks = AssertionChecks(graph, EvidenceChecks(graph.inputs))
    assert checks.assertion("teaching").state == "current"
    assert any(checks.edge(e) for e in graph.edges if e.assertion == "teaching")


def test_semantic_review_uses_full_exam_content_not_learner_progress_hash(tmp_path: Path) -> None:
    import json

    from tum_mcp.exam_content import concept_revision

    root = knowledge_project(tmp_path)
    before = concept_revision(read_exam(root).concepts[0])
    write_registry(root, [annotation(root, "exam/concept/observer")], reviewed=True)
    path = app_path(root, "exam.json")
    value = json.loads(path.read_bytes())
    value["concepts"][0]["details"].append(
        {
            "kind": "text",
            "title": "New condition",
            "sources": ["slides"],
            "paragraphs": ["A revised applicability explanation."],
        }
    )
    path.write_text(json.dumps(value), encoding="utf-8")
    assert concept_revision(read_exam(root).concepts[0]) == before
    graph = project(load_inputs(root))
    assert (
        AssertionChecks(graph, EvidenceChecks(graph.inputs)).assertion("teaching").state == "stale"
    )


def test_cyclic_and_wrong_role_annotations_never_activate(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    forward = annotation(root, key="forward") | {
        "relation": "prerequisite_of",
        "from": {"kind": "concept", "key": "observer"},
        "to": {"kind": "concept", "key": "coupling"},
    }
    backward = annotation(root, key="backward") | {
        "relation": "prerequisite_of",
        "from": {"kind": "concept", "key": "coupling"},
        "to": {"kind": "concept", "key": "observer"},
    }
    wrong = annotation(root, "lectures/lecture/observer-lecture", "wrong-role") | {
        "relation": "assesses"
    }
    write_registry(root, [forward, backward, wrong], reviewed=True)
    graph = project(load_inputs(root))
    checks = AssertionChecks(graph, EvidenceChecks(graph.inputs))
    assert checks.assertion("forward").state == checks.assertion("backward").state == "invalid"
    assert checks.assertion("wrong-role").problems == ("invalid_item_role",)


def test_candidate_that_would_close_a_cycle_is_not_ready(tmp_path: Path) -> None:
    import json

    from tum_mcp.study_store import private_path

    root = knowledge_project(tmp_path)
    forward = annotation(root, key="forward") | {
        "relation": "prerequisite_of",
        "from": {"kind": "concept", "key": "observer"},
        "to": {"kind": "concept", "key": "coupling"},
    }
    backward = annotation(root, key="backward") | {
        "relation": "prerequisite_of",
        "from": {"kind": "concept", "key": "coupling"},
        "to": {"kind": "concept", "key": "observer"},
    }
    write_registry(root, [forward, backward], reviewed=True)
    path = private_path(root, "knowledge.json")
    value = json.loads(path.read_bytes())
    value["assertions"][1]["review"] = {"status": "candidate", "revision": None}
    path.write_text(json.dumps(value))
    graph = project(load_inputs(root))
    checks = AssertionChecks(graph, EvidenceChecks(graph.inputs))
    assert checks.assertion("forward").state == "current"
    assert not checks.assertion("backward").ready_for_review
    assert checks.assertion("backward").problems == ("would_create_prerequisite_cycle",)


def test_cli_context_impact_schema_and_explicit_report(tmp_path: Path) -> None:
    import json

    from typer.testing import CliRunner

    from tum_mcp.cli import app

    root = knowledge_project(tmp_path)
    runner = CliRunner()
    for args in (
        ["context", str(root), "Observer", "--max-bytes", "2048"],
        ["impact", str(root), "--source", "slides"],
        ["schema", "knowledge"],
        ["report", str(root), "--section", "knowledge"],
    ):
        result = runner.invoke(app, ["study", *args])
        assert result.exit_code == 0, (result.output, result.exception)
        assert json.loads(result.output)
        if args[0] == "context":
            assert len(result.output.encode()) <= 2048
    result = runner.invoke(app, ["study", "report", str(root)])
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


def test_cli_malformed_knowledge_does_not_echo_input(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from tum_mcp.cli import app
    from tum_mcp.study_store import private_path

    root = knowledge_project(tmp_path)
    private_path(root, "knowledge.json").write_text('{"PRIVATE_SENTINEL":')
    for args in (
        ["context", str(root), "Observer"],
        ["report", str(root), "--section", "knowledge"],
    ):
        result = CliRunner().invoke(app, ["study", *args])
        assert result.exit_code != 0 and isinstance(result.exception, CampusError)
        assert "PRIVATE_SENTINEL" not in str(result.exception) + result.output


def test_cli_unknown_metadata_fields_never_echo_private_field_names(tmp_path: Path) -> None:
    import json

    from typer.testing import CliRunner

    from tum_mcp.cli import app
    from tum_mcp.study_store import private_path

    root = knowledge_project(tmp_path)
    write_registry(root, [annotation(root)])
    path = private_path(root, "knowledge.json")
    value = json.loads(path.read_bytes())
    value["PRIVATE_FIELD_SENTINEL"] = "PRIVATE_VALUE_SENTINEL"
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["study", "context", str(root), "Observer"])
    assert result.exit_code != 0 and isinstance(result.exception, CampusError)
    assert "PRIVATE" not in str(result.exception) + result.output
    assert "<field>" in str(result.exception)
    assert path.read_bytes() == before
