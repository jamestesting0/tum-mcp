from pathlib import Path

import pytest
from documents import content_file
from relations_fixture import knowledge_project, linked_project

from tum_mcp.course.project.store import load_state
from tum_mcp.course.relations.packet import encoded
from tum_mcp.course.relations.query import context, impact
from tum_mcp.errors import CampusError

pytestmark = pytest.mark.usefixtures("lecture_extension")


def test_context_four_homes_is_deterministic_safe_and_read_only(tmp_path: Path):
    root = linked_project(tmp_path)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    packet = context(root, concept="observer")
    assert {item["workspace"] for item in packet["items"]} == {
        "study",
        "exercises",
        "exam",
        "lectures",
    }
    assert packet["status"] == "ok"
    assert all(item["usable_as_evidence"] for item in packet["items"])
    output = encoded(packet)
    assert output == encoded(context(root, concept="observer"))
    assert b"SOLUTION_SECRET" not in output and b"https://" not in output
    assert b'"payload"' not in output and b'"recording"' not in output
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert len(encoded(context(root, concept="observer", max_bytes=2048))) <= 2048


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"query": ""},
        {"query": "x" * 501},
        {"query": "a", "concept": "b"},
        {"item": "unknown"},
        {"concept": "unknown"},
        {"query": "a", "purpose": "no"},
        {"query": "a", "limit": 0},
        {"query": "a", "max_bytes": 2047},
    ],
)
def test_invalid_context_selectors_fail_safely(tmp_path: Path, kwargs):
    with pytest.raises(CampusError):
        context(knowledge_project(tmp_path), **kwargs)


def test_impact_distinguishes_unknown_unmapped_direct_and_transitive(tmp_path: Path):
    root = knowledge_project(tmp_path)
    packet = impact(root, "missing")
    assert packet["unknown_source"] and packet["items"] == []
    state = load_state(root)
    unused = next(
        s.resource.key
        for s in state.resources
        if s.resource.key not in {"slides", "sheet", "lecture-summary"}
        and not any(s.resource.key == item["id"] for item in [])
    )
    # Even when the selected source is authored, the two dependency classes remain disjoint.
    packet = impact(root, "slides")
    assert packet["direct"] and not packet["unknown_source"]
    assert not set(packet["direct"]) & set(packet["review_candidates"])
    assert len(encoded(impact(root, unused, max_bytes=2048))) <= 2048


def test_uncertain_timed_evidence_never_becomes_supported_clarification(tmp_path: Path):
    import json

    root = knowledge_project(tmp_path)
    path = content_file(root, "lectures")
    value = json.loads(path.read_bytes())
    value["evidence"][0]["reviewed"] = False
    value["lectures"][0]["coverage"]["status"] = "partial"
    path.write_text(json.dumps(value))
    packet = context(root, item="lectures/lecture/observer-lecture/section/registration")
    section = next(item for item in packet["items"] if item["kind"] == "section")
    assert section["evidence_status"] == "stale" and not section["usable_as_evidence"]


def test_exam_packet_preserves_paper_and_official_solution_roles(tmp_path: Path):
    root = knowledge_project(tmp_path)
    ref = "exam/sitting/ws23/variant/ws23-a/question/ws23-a-1"
    packet = context(root, item=ref, purpose="exam")
    item = next(item for item in packet["items"] if item["id"] == ref)
    assert {row["role"] for row in item["source_roles"]} == {"paper", "official_solution"}
    assert item["tags"]["origin"] == "past"
    assert b"https://" not in encoded(packet) and b"SOLUTION_SECRET" not in encoded(packet)


def test_context_reports_native_reference_issues_omitted_by_its_cap(tmp_path: Path):
    import json

    root = knowledge_project(tmp_path, workspaces=frozenset({"study", "exercises"}))
    path = content_file(root, "study")
    value = json.loads(path.read_bytes())
    template = value["units"][0]
    value["units"].extend(template | {"key": f"extra-{i}"} for i in range(4))
    for i, unit in enumerate(value["units"]):
        unit["lectures"] = [f"missing-{i}-{j}" for j in range(6)]
    path.write_text(json.dumps(value))

    packet = context(root, item="study/unit/observer", max_bytes=65536)

    assert len(packet["issues"]) == 30
    assert packet["omitted"]["issues"] == 6
    assert packet["status"] == "partial"
