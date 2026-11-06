import json

from skill_lab import calibrate

from tum_mcp.course.content.store import read_document, write_document


def write_review(project, item, findings):
    path = project / ".tum-mcp/review/items" / f"{item}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "check": finding.get("check") or f"{finding['dimension']}.linked",
            "why": finding["note"],
            "status": finding.get("status", "open"),
        }
        for finding in findings
    ]
    path.write_text(json.dumps({"item": item, "findings": entries}))


def course(root):
    (root / "course/.tum-mcp").mkdir(parents=True)
    (root / "course/.tum-mcp/state.json").write_text("{}")
    text = {"kind": "text", "title": "Idea", "paragraphs": ["One. Two. Three.", "Four."]}
    unit = {"key": "unit", "blocks": [text, dict(text, title="Next"), dict(text, title="Last")]}
    write_document(root / "course", "study", {"units": [unit]})
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
    write_review(project, review["item"], review["findings"])
    content = json.dumps(read_document(project, "study")).replace(calibrate.META_LINE + " ", "")
    write_document(project, "study", json.loads(content))
    result = calibrate.recall(tmp_path, planted)
    assert result["recall"]["clarity"] == "1/1"
    assert result["recall"]["organization"] == "0/1"
    assert result["recall"]["cohesion"] == "2/2"


def test_old_findings_do_not_count_and_an_undone_defect_does(tmp_path):
    project = course(tmp_path)
    old = {"item": "study/unit", "findings": [{"dimension": "cohesion", "note": "Abrupt."}]}
    write_review(project, old["item"], old["findings"])
    planted = calibrate.plant(tmp_path)
    assert calibrate.recall(tmp_path, planted)["recall"]["cohesion"] == "0/2"
    # The reviewer gives the section an opening again without writing a finding.
    content = read_document(project, "study")
    next(b for b in content["units"][0]["blocks"] if b["title"] == "Last")["paragraphs"].insert(
        0, "Next builds on the idea."
    )
    write_document(project, "study", content)
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
    write_review(project, "study/unit", findings)
    result = calibrate.recall(tmp_path, planted)
    assert result["recall"]["cohesion"] == "0/2"
    assert result["rejected_share"] == 0.5


def test_catalogue_covers_ten_dimensions_without_breaking_content_schema(tmp_path):
    from importlib.resources import files

    from tum_mcp.course.content.exam import ExamContent
    from tum_mcp.course.content.study import StudyContent
    from tum_mcp.course.review.models import DIMENSIONS

    root = tmp_path / "course"
    (root / ".tum-mcp").mkdir(parents=True)
    (root / ".tum-mcp/state.json").write_text("{}")
    example = files("tum_mcp").joinpath("bundled/course_app/example")
    for workspace, name in (("study", "content.json"), ("exam", "exam.json")):
        write_document(root, workspace, json.loads(example.joinpath(name).read_bytes()))
    content = read_document(root, "study")
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
    write_document(root, "study", content)
    planted = calibrate.plant(tmp_path)
    assert {defect["dimension"] for defect in planted["defects"]} == set(DIMENSIONS)
    StudyContent.model_validate(read_document(root, "study"))
    ExamContent.model_validate(read_document(root, "exam"))
