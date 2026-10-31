"""Fixed synthetic gold refs; finder is a richer-corpus baseline, not a graph ablation."""

import json
import statistics
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path

import pytest
from knowledge_annotations import connected_annotations, write_registry
from knowledge_fixture import knowledge_project

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError
from tum_mcp.study_knowledge_evidence import EvidenceChecks
from tum_mcp.study_knowledge_packet import encoded
from tum_mcp.study_knowledge_projection import project
from tum_mcp.study_knowledge_query import _collect, context, impact, seeds
from tum_mcp.study_knowledge_store import load_inputs
from tum_mcp.study_store import confined, load_state, private_path
from tum_mcp.study_structure import course_map
from tum_mcp.study_text import find_sources

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures/study_knowledge/retrieval-cases.json").read_bytes()
)
ARTIFACTS = Path(".omo/evidence/study-knowledge-harness/implementation")


pytestmark = pytest.mark.usefixtures("course_memory")


def prepared(tmp_path):
    root = knowledge_project(tmp_path)
    write_registry(root, connected_annotations(root))
    path = private_path(root, "knowledge.json")
    value = json.loads(path.read_bytes())
    value["concepts"][0]["aliases"] += [
        "observer pattern",
        "registered observers",
        "notification mechanism",
        "subject notification",
    ]
    path.write_text(json.dumps(value))
    # Synthetic reviewed decisions, computed only after the equal-corpus aliases are fixed.
    from tum_mcp.study_knowledge_assertions import review_revision

    graph = project(load_inputs(root))
    for row in value["assertions"]:
        row["review"] = {
            "status": "reviewed",
            "revision": review_revision(graph, graph.assertions[row["key"]]),
        }
    path.write_text(json.dumps(value))
    return root


def native_baseline(root, selector, *, pages=False):
    graph = project(load_inputs(root))
    inputs = graph.inputs
    native_map = course_map(
        inputs.study, inputs.exercises, inputs.exam, inputs.lectures, ledger=inputs.ledger
    )
    assert native_map["workspaces"]
    graph.edges = {e for e in graph.edges if e.origin != "reviewed"}
    graph.assertions.clear()
    query = selector.get("query")
    if pages and query is not None:
        hits = find_sources(root, query, limit=8)
        selected = []
        for hit in hits["pages"]:
            for node in sorted(graph.nodes.values(), key=lambda n: n.id):
                if node.workspace not in {"study", "exercises", "exam", "lectures"}:
                    continue
                if not any(s.key == hit["key"] for s in node.sources):
                    continue
                page_range = node.payload.get("pages") if isinstance(node.payload, dict) else None
                if page_range:
                    first, _, last = page_range.partition("-")
                    if not int(first) <= hit["page"] <= int(last or first):
                        continue
                if node.id not in selected:
                    selected.append(node.id)
        selected = selected[:8]
    elif query is not None:
        selected, ambiguous = seeds(graph, query)
        if ambiguous:
            return {"items": [], "status": "ambiguous"}
    else:
        selected = [selector.get("item", f"concept/{selector.get('concept')}")]
    return _collect(graph, selected, selector, "study", 12, 24000)


def apply_change(root, change):
    if change in {"bytes", "missing_payload"}:
        source = next(s for s in load_state(root).resources if s.resource.key == "slides")
        path = confined(root, source.path)
        if change == "bytes":
            data = path.read_bytes()
            path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        else:
            path.unlink()
    elif change == "withdrawn":
        path = private_path(root, "state.json")
        value = json.loads(path.read_bytes())
        next(s for s in value["resources"] if s["resource"]["key"] == "slides")["status"] = (
            "withdrawn"
        )
        path.write_text(json.dumps(value))
    elif change == "uncertain":
        path = app_path(root, "lectures.json")
        value = json.loads(path.read_bytes())
        value["evidence"][0]["reviewed"] = False
        value["lectures"][0]["coverage"]["status"] = "partial"
        path.write_text(json.dumps(value))
    else:
        path = private_path(root, "knowledge.json")
        value = json.loads(path.read_bytes())
        if change in {"candidate", "rejected"}:
            value["assertions"][0]["review"] = {"status": change, "revision": None}
        elif change == "wrong_semester":
            value["semester"] = "another semester"
        else:
            value["assertions"][0]["from"]["ref"] = "study/unit/missing"
        path.write_text(json.dumps(value))


def safe_result(packet, forbidden=None):
    assert len(encoded(packet)) <= 24000
    assert b"SOLUTION_SECRET" not in encoded(packet)
    ids = {item["id"] for item in packet["items"] + packet.get("nodes", [])}
    assert all(set(path["nodes"]) <= ids for path in packet.get("paths", []))
    assert (
        all(
            step.get("assertion") != forbidden
            for path in packet.get("paths", [])
            for step in path["steps"]
        )
        if forbidden
        else True
    )


def test_fixed_retrieval_suite_and_two_existing_baselines(tmp_path: Path):
    results = []
    for case in CASES:
        folder = tmp_path / case["id"]
        folder.mkdir()
        root = prepared(folder)
        selector = case["selector"]
        if change := case.get("change"):
            apply_change(root, change)
        try:
            packet = (
                impact(root, selector["source"])
                if "source" in selector
                else context(root, **selector)
            )
        except CampusError:
            assert case.get("expected_status") == "error" or case.get("change") == "wrong_semester"
            results.append(
                {"id": case["id"], "group": case["group"], "safe": True, "status": "error"}
            )
            continue
        safe_result(packet, case.get("forbid_trusted_assertion"))
        expected = case.get("expected_status")
        if expected:
            assert (
                packet.get("unknown_source")
                if expected == "unknown_source"
                else packet["status"] == expected
            )
        required = set(case.get("required", []))
        ids = {item["id"] for item in packet["items"]}
        assert required <= ids, (case["id"], sorted(required - ids))
        row = {
            "id": case["id"],
            "group": case["group"],
            "safe": True,
            "graph_complete": required <= ids,
            "graph_items": sorted(ids),
            "bytes": len(encoded(packet)),
        }
        if case["group"] in {"bridge", "control"}:
            start = time.perf_counter()
            lexical = native_baseline(root, selector)
            row["lexical_seconds"] = time.perf_counter() - start
            start = time.perf_counter()
            cold = native_baseline(root, selector, pages=True)
            row["finder_cold_seconds"] = time.perf_counter() - start
            start = time.perf_counter()
            warm = native_baseline(root, selector, pages=True)
            row["finder_warm_seconds"] = time.perf_counter() - start
            row["lexical_complete"] = required <= {n["id"] for n in lexical["items"]}
            row["finder_complete"] = required <= {n["id"] for n in warm["items"]}
            assert cold["items"] == warm["items"]
            if case["group"] == "control":
                assert row["lexical_complete"] and row["finder_complete"]
        results.append(row)
    assert sum(r.get("graph_complete", False) for r in results if r["group"] == "bridge") >= 8
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "task-10-comparison.json").write_text(
        json.dumps(
            {
                "cases": results,
                "scope": "synthetic retrieval; no learning claim; finder raw corpus differs",
            },
            indent=2,
        )
    )


def test_safety_oracle_rejects_a_tempting_broken_result():
    import pytest

    with pytest.raises(AssertionError):
        safe_result(
            {"items": [], "paths": [{"nodes": [], "steps": [{"assertion": "stale"}]}]}, "stale"
        )


def test_three_hundred_unit_projection_and_payload_profile(tmp_path: Path):
    root = prepared(tmp_path)
    inputs = load_inputs(root)
    template = inputs.study.units[0]
    study = inputs.study.model_copy(
        update={
            "units": tuple(
                template.model_copy(update={"key": f"unit-{i}", "lectures": ()}) for i in range(300)
            )
        }
    )
    inputs = replace(inputs, study=study, registry=None)
    projection, verification = [], []
    tracemalloc.start()
    for _ in range(5):
        start = time.perf_counter()
        graph = project(inputs)
        projection.append(time.perf_counter() - start)
        checks = EvidenceChecks(inputs)
        start = time.perf_counter()
        for node in graph.nodes.values():
            for source in node.sources:
                checks.source(source)
        verification.append(time.perf_counter() - start)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "task-10-profile.json").write_text(
        json.dumps(
            {
                "units": 300,
                "runs": 5,
                "projection_median_seconds": statistics.median(projection),
                "verification_median_seconds": statistics.median(verification),
                "peak_python_bytes": peak,
                "source_payloads": len(checks.payloads),
            },
            indent=2,
        )
    )
