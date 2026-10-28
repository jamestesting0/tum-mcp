import json
from pathlib import Path

import pytest
from material_fixture import exam_document, exam_project, pdf_bytes

from tum_mcp.exam_content import ExamContent
from tum_mcp.exam_data import exam_report, exam_statistics, stale_exam
from tum_mcp.exam_layout import NODE_GAP, NODE_WIDTH, layout
from tum_mcp.study_store import load_state


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return exam_project(tmp_path_factory.mktemp("exam-data"))


@pytest.fixture(scope="module")
def content(project: Path) -> ExamContent:
    return ExamContent.model_validate(exam_document(project))


def test_frequencies_count_each_exam_once_and_skip_outdated_sittings(content: ExamContent) -> None:
    stats = exam_statistics(content)
    observer = stats["patterns"]["observer-design"]
    assert (observer["sittings_seen"], observer["sittings_considered"]) == (2, 2)
    assert (observer["variants_seen"], observer["variants_considered"]) == (3, 3)
    assert observer["last_seen"] == "2024-02" and observer["last_label"] == "Endterm WS23/24"
    strategy = stats["patterns"]["strategy-swap"]
    assert (strategy["sittings_seen"], strategy["variants_seen"]) == (1, 2)
    assert stats["pattern_order"] == ["observer-design", "composite-tree", "strategy-swap"]
    assert stats["points_known"] is False and observer["points_share"] is None
    assert stats["sittings_outdated"] == 1 and stats["years"] == ["2023", "2024"]
    assert stats["topic_shares"] == {
        "basis": "questions",
        "shares": {"behavioral": 0.8333, "structural": 0.1667},
    }
    assert stats["concepts"]["observer"]["sittings_seen"] == 2
    instances = {item["question"] for item in observer["instances"]}
    assert instances == {"ws23-a-1", "ws23-b-1", "ws22-1"}


def test_report_flags_targets_and_review_items_without_enforcing_them(content: ExamContent) -> None:
    report = exam_report(content)
    flags = {(item["item"], item["measure"]) for item in report["targets"]}
    assert ("mock:forecast-1", "estimated minutes vs duration") in flags
    assert ("mock:forecast-1", "points vs the real exam") in flags
    assert ("mock:forecast-1", "topic share gap (behavioral)") in flags
    assert report["uncovered_core"] == ["cohesion", "composite", "strategy"]
    assert {item["question"] for item in report["review"]} == {"ws22-2", "ss19-1"}
    mock = report["blueprint"]["mocks"][0]
    assert mock["points"] == 18 and mock["novelty"] == {"variant": 1, "untested": 1}
    json.dumps(report)


def test_layout_is_deterministic_layered_and_non_overlapping(content: ExamContent) -> None:
    first, second = layout(content), layout(content)
    assert first == second
    nodes = {node["key"]: node for node in first["nodes"]}
    assert set(nodes) == {"observer", "loose-coupling", "strategy", "composite", "decorator"}
    assert nodes["loose-coupling"]["depth"] == 0 and nodes["observer"]["depth"] == 1
    assert nodes["decorator"]["depth"] == 0
    assert [column["topic"] for column in first["columns"]] == ["behavioral", "structural"]
    rows: dict[tuple[int, int], list[int]] = {}
    for node in first["nodes"]:
        rows.setdefault((node["column"], node["y"]), []).append(node["x"])
        assert 0 <= node["x"] and node["x"] + NODE_WIDTH <= first["width"]
        assert node["y"] + first["node_height"] <= first["height"]
    for xs in rows.values():
        xs.sort()
        assert all(
            right - left >= NODE_WIDTH + NODE_GAP for left, right in zip(xs, xs[1:], strict=False)
        )
    assert first["overview"]["links"] == []


def test_changed_sources_mark_only_dependent_items_stale(tmp_path: Path) -> None:
    root = exam_project(tmp_path)
    content = ExamContent.model_validate(exam_document(root))
    assert stale_exam(root, load_state(root), content) == ()
    (root / "materials/exams/material-exam-ws22-upload.pdf").write_bytes(pdf_bytes(["Edited"]))
    assert stale_exam(root, load_state(root), content) == ("variant:ws22-a",)
