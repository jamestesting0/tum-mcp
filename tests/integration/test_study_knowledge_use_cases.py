"""Evidence/side-effect checks support, but cannot grade, proposed tutoring decisions."""

import json
from pathlib import Path

import pytest
from knowledge_fixture import linked_project

from tum_mcp.course.memory.packet import encoded
from tum_mcp.course.memory.query import context, impact

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures/study_knowledge/use-cases.json").read_bytes()
)


pytestmark = pytest.mark.usefixtures("lecture_extension")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_tutoring_use_case_evidence_and_read_only_scope(tmp_path: Path, case):
    root = linked_project(tmp_path, workspaces=frozenset(case["available_workspaces"]))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    selector = case["selector"]
    packet = impact(root, selector["source"]) if "source" in selector else context(root, **selector)
    ids = {item["id"] for item in packet["items"]}
    assert set(case["expected_refs"]) <= ids
    if case["id"] == "U1":
        assert packet["status"] == "empty" and packet["scope"]["present"] == []
    if case["id"] == "U12":
        selected = next(item for item in packet["items"] if item["id"] in case["expected_refs"])
        assert selected["tags"]["role"] == "enrichment"
    assert b"SOLUTION_SECRET" not in encoded(packet)
    assert "mastery" not in packet and "readiness" not in packet
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
