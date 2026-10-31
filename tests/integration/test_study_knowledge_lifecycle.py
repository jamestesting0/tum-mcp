"""Source lifecycle tests use local bytes and never a campus connection."""

import json
from pathlib import Path

import pytest
from knowledge_fixture import knowledge_project
from knowledge_lecture_fixture import real_cached_lecture

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_knowledge_evidence import EvidenceChecks
from tum_mcp.study_knowledge_models import SourceEvidence, SupportGroup
from tum_mcp.study_knowledge_store import load_inputs
from tum_mcp.study_store import load_state, private_path

pytestmark = pytest.mark.usefixtures("course_memory")


def test_support_alternatives_preserve_relation_but_never_repair_stale_owner(tmp_path: Path):
    from knowledge_annotations import annotation, write_registry

    from tum_mcp.study_knowledge_assertions import AssertionChecks
    from tum_mcp.study_knowledge_projection import project

    root = knowledge_project(tmp_path)
    other = next(s for s in load_state(root).resources if s.resource.key != "slides")
    teaching = annotation(root)
    alternative = {
        "key": "independent",
        "evidence": [{"kind": "source", "source": other.resource.key, "sha256": other.sha256}],
    }
    teaching["support_groups"].append(alternative)
    relation = annotation(root, key="relation") | {
        "relation": "prerequisite_of",
        "from": {"kind": "concept", "key": "observer"},
        "to": {"kind": "concept", "key": "coupling"},
        "support_groups": teaching["support_groups"],
    }
    write_registry(root, [teaching, relation], reviewed=True)
    state = load_state(root)
    state = state.model_copy(
        update={
            "resources": tuple(
                s.model_copy(update={"status": "withdrawn"}) if s.resource.key == "slides" else s
                for s in state.resources
            )
        }
    )
    private_path(root, "state.json").write_text(state.model_dump_json())
    graph = project(load_inputs(root))
    checks = AssertionChecks(graph, EvidenceChecks(graph.inputs))
    assert checks.assertion("relation").state == "current"
    assert checks.assertion("teaching").state == "invalid"
    assert [g.current for g in checks.assertion("relation").groups] == [False, True]


def test_unkeyed_and_repeated_passages_have_only_stable_owner_anchors(tmp_path: Path):
    from tum_mcp.study_knowledge_projection import project

    root = knowledge_project(tmp_path)
    path = app_path(root, "content.json")
    value = json.loads(path.read_bytes())
    blocks = value["units"][0]["blocks"]
    blocks.append(dict(blocks[0]))
    value["units"][1]["blocks"][0].pop("key", None)
    path.write_text(json.dumps(value))
    # This native schema already rejects duplicate passage keys; preserve that gate.
    with pytest.raises(CampusError, match="Invalid content.json"):
        load_inputs(root)
    blocks.pop()
    blocks[0].pop("key")
    path.write_text(json.dumps(value))
    graph = project(load_inputs(root))
    assert "study/unit/observer" in graph.nodes
    assert "study/unit/observer/block/observer-definition" not in graph.nodes
    assert any(issue.code == "missing_reference" for issue in graph.issues)


@pytest.mark.parametrize("exercises,lectures", [(False, False), (True, True)])
def test_registry_and_packets_never_enter_site_exports(
    tmp_path: Path, lecture_extension: Path, exercises, lectures
):
    from knowledge_annotations import annotation, write_registry

    from tum_mcp.study_build import build
    from tum_mcp.study_knowledge_query import context
    from tum_mcp.study_publish_site import export_site

    root = knowledge_project(tmp_path)
    row = annotation(root) | {"rationale": "PRIVATE_KNOWLEDGE_SENTINEL"}
    write_registry(root, [row], reviewed=True)
    packet = context(root, concept="observer")
    assert "PRIVATE_KNOWLEDGE_SENTINEL" in json.dumps(packet)
    private_path(root, "context.json").write_text(json.dumps(packet))
    build(root, publish=False)
    output = export_site(root, include_exercises=exercises, include_lectures=lectures)
    exported = b"".join(output.values())
    assert b"PRIVATE_KNOWLEDGE_SENTINEL" not in exported
    assert b"knowledge.json" not in exported
    assert private_path(root, "knowledge.json").exists()


def files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_retired_and_pending_memory_stay_inactive_without_erasing_history(tmp_path: Path):
    from knowledge_annotations import annotation, write_registry

    from tum_mcp.study_knowledge_query import context
    from tum_mcp.study_knowledge_report import knowledge_report

    root = knowledge_project(tmp_path)
    replacement = annotation(root, key="replacement")
    write_registry(root, [replacement], reviewed=True)
    path = private_path(root, "knowledge.json")
    registry = json.loads(path.read_bytes())
    retired = annotation(root, key="retired") | {
        "conditions": ["Earlier unqualified formulation."],
        "rationale": "Rejected in favor of replacement, which states registration explicitly.",
        "review": {"status": "rejected", "revision": None},
    }
    pending = annotation(root, "study/unit/strategy", "pending") | {
        "rationale": "Unresolved comparison awaiting actual evidence review."
    }
    registry["assertions"].extend([retired, pending])
    path.write_text(json.dumps(registry))
    note = private_path(root, "notes/personal.md")
    note.parent.mkdir(exist_ok=True)
    note.write_text("Keep my explicit study preference and personal notes.\n")
    before = files(root)

    report = knowledge_report(root)
    assert {row["key"]: row["state"] for row in report["assertions"]} == {
        "replacement": "current",
        "retired": "rejected",
        "pending": "candidate",
    }
    packet = context(root, concept="observer")
    assertions = {
        step["assertion"]
        for route in packet["paths"]
        for step in route["steps"]
        if step.get("assertion")
    }
    assert assertions == {"replacement"}
    ambiguous = context(root, "Notification pattern")
    assert ambiguous["status"] == "ambiguous" and len(ambiguous["candidates"]) == 2
    assert ambiguous["items"] == ambiguous["paths"] == []
    assert files(root) == before


@pytest.mark.parametrize("layout", [("app", ".tum-mcp"), ("study", ".study")])
def test_snapshot_is_read_only_with_missing_optional_registry(tmp_path: Path, layout) -> None:
    root = knowledge_project(tmp_path, layout)
    before = files(root)
    inputs = load_inputs(root)
    assert inputs.workspaces == ("study", "exercises", "exam", "lectures")
    checks = EvidenceChecks(inputs)
    assert all(checks.source(s).current for s in inputs.study.units[0].sources)
    assert checks.lecture("observer-lecture").current
    assert len(inputs.reader.verify()) == 64
    assert files(root) == before


@pytest.mark.parametrize("change", ["authored", "new-registry", "source", "migration"])
def test_snapshot_detects_changes_between_read_and_return(tmp_path: Path, change: str) -> None:
    root = knowledge_project(tmp_path)
    inputs = load_inputs(root)
    EvidenceChecks(inputs).source(inputs.study.units[0].sources[0])
    match change:
        case "authored":
            path = app_path(root, "content.json")
            value = json.loads(path.read_bytes())
            value["introduction"] += " Changed."
            path.write_text(json.dumps(value), encoding="utf-8")
        case "new-registry":
            private_path(root, "knowledge.json").write_text("{}", encoding="utf-8")
        case "source":
            path = root / inputs.resources["slides"].path
            path.write_bytes(path.read_bytes().replace(b"Observer", b"Strategy"))
        case "migration":
            (root / ".tum-mcp/migration.lock").write_text("interrupted", encoding="utf-8")
    with pytest.raises(CampusError) as error:
        inputs.reader.verify()
    assert error.value.code in {Code.STALE_RESULT, Code.WORKSPACE_CONFLICT}


def test_evidence_hashes_actual_bytes_not_inventory_generation(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    inputs = load_inputs(root)
    version = inputs.study.units[0].sources[0]
    path = root / inputs.resources[version.key].path
    original = path.read_bytes()
    path.write_bytes(original.replace(b"Observer", b"Strategy"))
    checks = EvidenceChecks(load_inputs(root))
    assert checks.source(version).state == "stale"
    path.write_bytes(original)
    assert EvidenceChecks(load_inputs(root)).source(version).current


def test_independent_and_conjunctive_evidence_are_distinct(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    state = load_state(root)
    refs = [
        SourceEvidence(kind="source", source=s.resource.key, sha256=s.sha256)
        for s in state.resources[:2]
    ]
    independent = [SupportGroup(key=f"g{i}", evidence=(ref,)) for i, ref in enumerate(refs)]
    joint = SupportGroup(key="together", evidence=tuple(refs))
    value = state.model_dump(mode="json")
    value["resources"][0]["status"] = "withdrawn"
    private_path(root, "state.json").write_text(json.dumps(value), encoding="utf-8")
    checks = EvidenceChecks(load_inputs(root))
    assert any(checks.group(group).current for group in independent)
    assert not checks.group(joint).current


@pytest.mark.parametrize("change", ["malformed", "scope", "semester", "symlink"])
def test_snapshot_boundary_errors_preserve_private_inputs(tmp_path: Path, change: str) -> None:
    root = knowledge_project(tmp_path)
    match change:
        case "malformed":
            app_path(root, "content.json").write_text("PRIVATE_SENTINEL", encoding="utf-8")
        case "scope":
            path = app_path(root, "exercises.json")
            value = json.loads(path.read_bytes()) | {"course_key": "another-course"}
            path.write_text(json.dumps(value), encoding="utf-8")
        case "semester":
            private_path(root, "knowledge.json").write_text(
                json.dumps({"course_key": "synthetic-pse-ws26", "semester": "another-semester"}),
                encoding="utf-8",
            )
        case "symlink":
            path = app_path(root, "content.json")
            path.rename(root / "saved.json")
            try:
                path.symlink_to(root / "saved.json")
            except OSError:
                pytest.skip("This host does not permit synthetic symlinks.")
    before = files(root)
    with pytest.raises(CampusError) as error:
        load_inputs(root)
    assert "PRIVATE_SENTINEL" not in str(error.value)
    assert files(root) == before


def test_lecture_snapshot_observes_receipt_transcript_and_absent_progress(tmp_path: Path) -> None:
    root = real_cached_lecture(tmp_path)
    inputs = load_inputs(root)
    assert EvidenceChecks(inputs).lecture("observer-lecture").current
    inputs.reader.verify()
    cache = private_path(root, "lectures/live-42-11")
    (cache / "progress.json").write_text(
        json.dumps({"metadata_revision": "c" * 64, "stage": "interrupted"}), encoding="utf-8"
    )
    with pytest.raises(CampusError, match="changed"):
        inputs.reader.verify()
    assert not EvidenceChecks(load_inputs(root)).lecture("observer-lecture").current
    (cache / "progress.json").unlink()
    (cache / "transcript.json").write_bytes(b"[ ]")
    assert not EvidenceChecks(load_inputs(root)).lecture("observer-lecture").current


@pytest.mark.parametrize("failure", ["source-frame", "forged-crop"])
def test_lecture_snapshot_checks_original_frames_and_verified_crops(
    tmp_path: Path, failure: str
) -> None:
    root = real_cached_lecture(tmp_path, with_frame=True)
    before = files(root)
    inputs = load_inputs(root)
    assert EvidenceChecks(inputs).lecture("observer-lecture").current
    inputs.reader.verify()
    assert files(root) == before
    if failure == "source-frame":
        path = next(private_path(root, "lectures/live-42-11/frames").glob("*.png"))
        path.write_bytes(b"changed original frame")
    else:
        path = app_path(root, "lectures.json")
        value = json.loads(path.read_bytes())
        figure = value["lectures"][0]["sections"][0]["figures"][0]
        figure["sha256"] = "f" * 64
        figure["asset"] = "lecture-assets/" + "f" * 64 + ".png"
        path.write_text(json.dumps(value), encoding="utf-8")
    assert not EvidenceChecks(load_inputs(root)).lecture("observer-lecture").current
