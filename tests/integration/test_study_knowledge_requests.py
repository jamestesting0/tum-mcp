from pathlib import Path

import pytest
from knowledge_annotations import connected_annotations, write_registry
from knowledge_fixture import knowledge_project

from tum_mcp.errors import CampusError
from tum_mcp.study_knowledge_packet import encoded
from tum_mcp.study_knowledge_query import context, impact
from tum_mcp.study_knowledge_report import knowledge_report
from tum_mcp.study_store import load_state

pytestmark = pytest.mark.usefixtures("course_memory")


def test_context_four_homes_is_deterministic_safe_and_read_only(tmp_path: Path):
    root = knowledge_project(tmp_path)
    write_registry(root, connected_annotations(root), reviewed=True)
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


def test_ambiguous_alias_has_no_semantic_paths(tmp_path: Path):
    root = knowledge_project(tmp_path)
    write_registry(root, connected_annotations(root), reviewed=True)
    packet = context(root, "Notification pattern")
    assert packet["status"] == "ambiguous" and len(packet["candidates"]) == 2
    assert packet["items"] == packet["paths"] == []


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


def test_full_report_exposes_expected_receipt_without_approving(tmp_path: Path):
    root = knowledge_project(tmp_path)
    write_registry(root, connected_annotations(root))
    report = knowledge_report(root)
    assert report["knowledge_revision"] is None
    assert all(
        row["state"] == "candidate" and row["expected_revision"] and row["ready_for_review"]
        for row in report["assertions"]
    )


def test_uncertain_timed_evidence_never_becomes_supported_clarification(tmp_path: Path):
    import json

    from tum_mcp.course_app_paths import app_path

    root = knowledge_project(tmp_path)
    path = app_path(root, "lectures.json")
    value = json.loads(path.read_bytes())
    value["evidence"][0]["reviewed"] = False
    value["lectures"][0]["coverage"]["status"] = "partial"
    path.write_text(json.dumps(value))
    packet = context(root, item="lectures/lecture/observer-lecture/section/registration")
    section = next(item for item in packet["items"] if item["kind"] == "section")
    assert section["evidence_status"] == "stale" and not section["usable_as_evidence"]
    write_registry(root, connected_annotations(root), reviewed=True)
    row = next(row for row in knowledge_report(root)["assertions"] if row["key"] == "lecture")
    assert row["state"] == "invalid"


def test_exam_packet_preserves_paper_and_official_solution_roles(tmp_path: Path):
    root = knowledge_project(tmp_path)
    ref = "exam/sitting/ws23/variant/ws23-a/question/ws23-a-1"
    packet = context(root, item=ref, purpose="exam")
    item = next(item for item in packet["items"] if item["id"] == ref)
    assert {row["role"] for row in item["source_roles"]} == {"paper", "official_solution"}
    assert item["tags"]["origin"] == "past"
    assert b"https://" not in encoded(packet) and b"SOLUTION_SECRET" not in encoded(packet)


@pytest.mark.parametrize("max_bytes", [65536, 2048])
def test_impact_reports_assertion_diagnostics_omitted_by_its_key_cap(tmp_path: Path, max_bytes):
    from knowledge_annotations import annotation

    root = knowledge_project(tmp_path)
    rows = [
        annotation(root, key=f"candidate-{i}-" + "x" * 80) | {"conditions": [f"Toy scope {i}."]}
        for i in range(31)
    ]
    write_registry(root, rows)

    packet = impact(root, "slides", max_bytes=max_bytes)

    assert len(packet["assertion_candidates"]) <= 30
    assert len(packet["assertion_candidates"]) + packet["omitted"]["assertion_candidates"] == 31
    assert len(encoded(packet)) <= max_bytes
    assert set(packet["assertion_candidates"]) <= {row["key"] for row in rows}
    assert packet["status"] == "partial"


def test_context_reports_native_reference_issues_omitted_by_its_cap(tmp_path: Path):
    import json

    root = knowledge_project(tmp_path, workspaces=frozenset({"study", "exercises"}))
    path = root / "app/content.json"
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
