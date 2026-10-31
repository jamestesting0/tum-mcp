"""Deterministic work regressions; timings are explicit local evidence, never a CI gate."""

import json
import os
from pathlib import Path

import pytest
from course_memory_profile import profile, scaled_course

from tum_mcp.study_knowledge_store import load_inputs

pytestmark = pytest.mark.usefixtures("course_memory")


def test_crowded_profile_respects_native_schema_and_snapshot(tmp_path: Path):
    root = scaled_course(tmp_path, 10, crowded=True)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    inputs = load_inputs(root)
    assert len(inputs.study.units) == 10
    assert all(len(u.blocks) == 20 for u in inputs.study.units)
    inputs.reader.verify()
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_MEMORY_PROFILE") != "1", reason="local profiling opt-in"
)
def test_profile_course_memory(tmp_path: Path):
    output = Path(os.environ["TUM_MCP_MEMORY_PROFILE_OUTPUT"]).resolve()
    repo = Path(__file__).resolve().parents[2]
    assert output.is_relative_to(repo / ".omo/evidence/course-memory-optimization")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile(tmp_path), indent=2), encoding="utf-8")


def test_resource_lookup_is_request_local_and_replaced_with_state(tmp_path: Path):
    from dataclasses import replace

    root = scaled_course(tmp_path, 14)
    inputs = load_inputs(root)
    resources = inputs.resources
    assert resources is inputs.resources
    with pytest.raises(TypeError):
        resources["invented"] = next(iter(resources.values()))
    state = inputs.state.model_copy(update={"resources": ()})
    assert not replace(inputs, state=state).resources
    assert resources and load_inputs(root).resources == resources


def test_small_packet_avoids_validating_discarded_native_candidates(tmp_path: Path):
    from course_memory_profile import measured_context

    root = scaled_course(tmp_path, 10, crowded=True)
    result = measured_context(root)
    assert result["ids"] == [
        "study/unit/unit-000",
        "exercises/set/sheet-1/exercise/observer-practice",
        "study/unit/unit-001",
        "study/unit/unit-002",
    ]
    assert result["status"] == "ok"
    assert result["work"]["item_views"] <= 46  # At least 80% less than the frozen 232-view case.
    assert result["work"]["initial_hash_calls"] <= 5


@pytest.mark.parametrize("limit", [1, 4, 12])
def test_selection_skips_stale_top_home_and_preserves_workspace_reservations(tmp_path: Path, limit):
    from tum_mcp.study_knowledge_query import context

    root = scaled_course(tmp_path, 10, crowded=True)
    (root / "materials/content/material-source-000.md").write_text("Changed evidence.")
    packet = context(root, item="exercises/set/sheet-1/exercise/observer-practice", limit=limit)
    assert packet["items"][0]["id"] == "study/unit/unit-001"
    assert all(item["evidence_status"] == "current" for item in packet["items"])
    assert all("unit-000" not in item["id"] for item in packet["items"])
    if limit >= 4:
        assert {i["workspace"] for i in packet["items"]} == {"study", "exercises"}


@pytest.mark.parametrize(
    "case",
    json.loads(
        (Path(__file__).parents[1] / "fixtures/study_knowledge/efficiency-cases.json").read_bytes()
    ),
)
def test_natural_query_quality_contract(tmp_path: Path, case):
    from knowledge_annotations import annotation, write_registry
    from knowledge_fixture import knowledge_project

    from tum_mcp.study_knowledge_query import context

    root = knowledge_project(tmp_path, workspaces=frozenset({"study"}))
    write_registry(root, [annotation(root)], reviewed=True)
    packet = context(root, case["query"])
    if case.get("required"):
        assert case["required"] in {i["id"] for i in packet["items"]}
    if case.get("ambiguous"):
        assert packet["status"] == "ambiguous" and not packet["items"]
    if case.get("empty"):
        assert packet["status"] == "empty" and not packet["items"]
