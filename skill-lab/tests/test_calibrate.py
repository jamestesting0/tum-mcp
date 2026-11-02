import json

from skill_lab import calibrate


def course(root):
    (root / "course/.tum-mcp").mkdir(parents=True)
    (root / "course/.tum-mcp/state.json").write_text("{}")
    (root / "course/app").mkdir()
    text = {"kind": "text", "title": "Idea", "paragraphs": ["One. Two. Three.", "Four."]}
    unit = {"key": "unit", "blocks": [text, dict(text, title="Next"), dict(text, title="Last")]}
    (root / "course/app/content.json").write_text(json.dumps({"units": [unit]}))
    return root / "course"


def test_a_review_that_notes_or_fixes_a_planted_defect_finds_it(tmp_path):
    project = course(tmp_path)
    planted = calibrate.plant(tmp_path)
    names = {item["defect"] for item in planted["defects"]}
    assert {"meta_line", "point_last", "dropped_link"} <= names
    # The review notes the cohesion defects and fixes the meta line without a finding.
    review = {
        "item": "study/unit",
        "findings": [
            {"dimension": "cohesion", "check": "cohesion.point_first", "note": "Point last."},
            {"dimension": "cohesion", "check": "cohesion.linked", "note": "Abrupt."},
        ],
    }
    (project / ".tum-mcp/review.json").write_text(json.dumps({"reviews": [review]}))
    content = (project / "app/content.json").read_text().replace(calibrate.META_LINE + " ", "")
    (project / "app/content.json").write_text(content)
    result = calibrate.recall(tmp_path, planted)
    assert result["recall"]["clarity"] == "1/1"
    assert result["recall"]["organization"] == "0/1"
    assert result["recall"]["cohesion"] == "2/2"


def test_old_findings_do_not_count_and_an_undone_defect_does(tmp_path):
    project = course(tmp_path)
    old = {"item": "study/unit", "findings": [{"dimension": "cohesion", "note": "Abrupt."}]}
    (project / ".tum-mcp/review.json").write_text(json.dumps({"reviews": [old]}))
    planted = calibrate.plant(tmp_path)
    assert calibrate.recall(tmp_path, planted)["recall"]["cohesion"] == "0/2"
    # The reviewer gives the section an opening again without writing a finding.
    path = project / "app/content.json"
    content = json.loads(path.read_text())
    next(b for b in content["units"][0]["blocks"] if b["title"] == "Last")["paragraphs"].insert(
        0, "Next builds on the idea."
    )
    path.write_text(json.dumps(content))
    assert calibrate.recall(tmp_path, planted)["recall"]["cohesion"] == "1/2"


def test_rejected_or_unrelated_findings_do_not_inflate_recall(tmp_path):
    project = course(tmp_path)
    planted = calibrate.plant(tmp_path)
    findings = [
        {
            "dimension": "cohesion",
            "check": "cohesion.linked",
            "status": "rejected",
            "note": "Wrong.",
        },
        {"dimension": "cohesion", "check": "cohesion.one_term", "note": "Different issue."},
    ]
    (project / ".tum-mcp/review.json").write_text(
        json.dumps({"reviews": [{"item": "study/unit", "findings": findings}]})
    )
    result = calibrate.recall(tmp_path, planted)
    assert result["recall"]["cohesion"] == "0/2"
    assert result["rejected_share"] == 0.5


def test_catalogue_covers_ten_dimensions_without_breaking_content_schema(tmp_path):
    from importlib.resources import files

    from tum_mcp.exam_content import ExamContent
    from tum_mcp.study_content import StudyContent
    from tum_mcp.study_review import DIMENSIONS

    root = tmp_path / "course"
    (root / ".tum-mcp").mkdir(parents=True)
    (root / ".tum-mcp/state.json").write_text("{}")
    (root / "app").mkdir()
    example = files("tum_mcp").joinpath("bundled/course_app/example")
    for name in ("content.json", "exam.json"):
        (root / "app" / name).write_bytes(example.joinpath(name).read_bytes())
    path = root / "app/content.json"
    content = json.loads(path.read_text())
    unit = content["units"][-1]
    unit["blocks"].append(
        {
            "kind": "text",
            "title": "A separate calculation",
            "sources": [unit["sources"][0]["key"]],
            "paragraphs": [
                "Compute the cost along the first path. Keep each intermediate value.",
                "Compute the cost along the second path. Compare the two totals.",
            ],
        }
    )
    path.write_text(json.dumps(content))
    planted = calibrate.plant(tmp_path)
    assert {defect["dimension"] for defect in planted["defects"]} == set(DIMENSIONS)
    StudyContent.model_validate_json((root / "app/content.json").read_bytes())
    ExamContent.model_validate_json((root / "app/exam.json").read_bytes())
