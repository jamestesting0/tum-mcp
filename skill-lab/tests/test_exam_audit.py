import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/integration"))

from material_fixture import exam_document, exam_project  # noqa: E402
from skill_lab import calibrate, exam_audit  # noqa: E402

from tum_mcp.course.content.exam import ExamContent  # noqa: E402


def test_audit_counts_the_synthetic_exam(tmp_path: Path) -> None:
    document = exam_document(exam_project(tmp_path))
    facts = exam_audit.audit_content(ExamContent.model_validate(document))

    questions = [q for s in document["sittings"] for v in s["variants"] for q in v["questions"]]
    assert sum(facts["question_status"].values()) == len(questions)
    assert set(facts["patterns"]) == {pattern["key"] for pattern in document["patterns"]}
    assert len(facts["sittings"]) == len(document["sittings"])
    assert facts["concepts"]["total"] == len(document["concepts"])
    assert all(
        facts["patterns"][key]["past_instances"] <= 1 for key in facts["single_instance_patterns"]
    )


def test_a_project_without_exam_has_no_audit(tmp_path: Path) -> None:
    assert exam_audit.audit(tmp_path) is None


def test_exam_plants_keep_the_exam_valid_and_name_their_checks(tmp_path: Path) -> None:
    document = exam_document(exam_project(tmp_path))
    planted = calibrate._exam_defects(document)
    ExamContent.model_validate(document)
    assert {item["defect"] for item in planted} <= set(calibrate.EXAM_CHECKS)
    assert "xm_meta_summary" in {item["defect"] for item in planted}
    for item in planted:
        assert item["probe"] in str(document)
