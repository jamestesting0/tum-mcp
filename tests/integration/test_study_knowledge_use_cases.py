"""Evidence/side-effect checks support, but cannot grade, proposed tutoring decisions."""

import json
from pathlib import Path

import pytest
from knowledge_annotations import annotation, connected_annotations, write_registry
from knowledge_fixture import knowledge_project

from tum_mcp.study_knowledge_packet import encoded
from tum_mcp.study_knowledge_query import context, impact

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures/study_knowledge/use-cases.json").read_bytes()
)


pytestmark = pytest.mark.usefixtures("course_memory")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_tutoring_use_case_evidence_and_read_only_scope(tmp_path: Path, case):
    root = knowledge_project(tmp_path, workspaces=frozenset(case["available_workspaces"]))
    if case["available_workspaces"]:
        foundation = annotation(root, key="foundation") | {
            "relation": "prerequisite_of",
            "from": {"kind": "concept", "key": "observer"},
            "to": {"kind": "concept", "key": "coupling"},
        }
        contrast = annotation(root, key="contrast") | {
            "relation": "contrasts",
            "from": {"kind": "concept", "key": "observer"},
            "to": {"kind": "concept", "key": "coupling"},
            "conditions": ["Notification behavior is compared only after registration."],
        }
        write_registry(root, [*connected_annotations(root), foundation, contrast], reviewed=True)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    selector = case["selector"]
    packet = impact(root, selector["source"]) if "source" in selector else context(root, **selector)
    ids = {item["id"] for item in packet["items"]}
    assert set(case["expected_refs"]) <= ids
    if case["id"] == "U1":
        assert packet["status"] == "empty" and packet["scope"]["present"] == []
    if case["id"] == "U5":
        prerequisite = next(
            step
            for path in packet["paths"]
            for step in path["steps"]
            if step["relation"] == "prerequisite_of"
        )
        assert (
            prerequisite["from"] == "concept/observer" and prerequisite["to"] == "concept/coupling"
        )
    if case["id"] == "U12":
        selected = next(item for item in packet["items"] if item["id"] in case["expected_refs"])
        assert selected["tags"]["role"] == "enrichment"
    if case["id"] == "U13":
        assert any(step["conditions"] for path in packet["paths"] for step in path["steps"])
    assert b"SOLUTION_SECRET" not in encoded(packet)
    assert "mastery" not in packet and "readiness" not in packet
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
