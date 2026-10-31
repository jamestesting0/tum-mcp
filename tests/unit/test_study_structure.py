import copy
import json
from pathlib import Path

from tum_mcp.exam_content import Concept, ExamContent
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.lecture_content import LectureContent
from tum_mcp.study_content import StudyContent
from tum_mcp.study_structure import course_map, structure_flags, structure_revision

FIXTURES = Path(__file__).parents[1] / "fixtures"
PASSAGE = (
    "Relaxation keeps the cheaper of two routes: the distance already stored for a node, or the "
    "distance of its neighbour plus the cost of the edge between them, so every update can only "
    "lower a stored value and never raise it again."
)


def study() -> dict:
    return json.loads((FIXTURES / "course_app/content.json").read_bytes())


def exercises() -> dict:
    return json.loads((FIXTURES / "exercises.json").read_bytes())


def flags(content: dict, sheets: dict | None = None, **others) -> set[tuple[str, str]]:
    found = structure_flags(
        StudyContent.model_validate(content),
        ExerciseContent.model_validate(sheets) if sheets else None,
        others.get("exam"),
        others.get("lectures"),
    )
    return {(entry["flag"], entry["item"]) for entry in found}


def test_flags_terms_used_too_early_and_groups_that_do_not_help_find_a_unit() -> None:
    # Given the synthetic course: one unit under Foundations beside three under Algorithms,
    # which split again into two subgroups, and a lone unit under Mathematics / Probability.
    content = study()
    found = flags(content)
    # Then lone units beside larger groups, and small groups split again, are flagged.
    assert ("singleton_category", "study/graphs") in found
    assert ("singleton_category", "study/weighted") in found
    assert ("deep_category", "outline") in found
    assert not {kind for kind, _ in found} & {"forward_term", "near_duplicate_passage"}
    # Lecture groups follow the calendar, so a lecture with one unit is not flagged.
    lectures = flags(content | {"organization": "lectures"})
    assert "singleton_category" not in {kind for kind, _ in lectures}
    # When an earlier unit marks a term that only a later unit defines.
    bfs = next(unit for unit in content["units"] if unit["key"] == "bfs")
    bfs["blocks"][0]["paragraphs"] = ["Each node keeps a {{tentative distance}} from the start."]
    assert ("forward_term", "study/bfs") in flags(content)
    # A catch-all label and a unit outside every group are flagged too.
    bfs["path"] = ["Misc"]
    content["units"][-1]["path"] = []
    found = flags(content)
    assert ("catch_all_category", "outline") in found
    assert ("ungrouped_unit", "outline") in found


def test_flags_a_section_that_returns_to_much_earlier_source_pages() -> None:
    # Given a unit whose sections follow the lecture's pages, then one appended from its start.
    content = study()
    unit = next(unit for unit in content["units"] if unit["key"] == "weighted")
    titled = [block for block in unit["blocks"] if block.get("title")]
    for index, block in enumerate(titled):
        block["pages"] = f"{20 + 10 * index}-{21 + 10 * index}"
    assert ("source_order", "study/weighted") not in flags(content)
    # When the last section cites page 4.
    titled[-1]["pages"] = "4-7"
    # Then the unit is flagged; a small step back stays quiet.
    assert ("source_order", "study/weighted") in flags(content)
    titled[-1]["pages"] = str(int(titled[-2]["pages"].split("-")[0]) - 5)
    assert ("source_order", "study/weighted") not in flags(content)


def test_long_flat_outlines_are_reviewed_and_heading_edits_stale_the_course() -> None:
    content = study()
    unit = content["units"][0]
    source = unit["sources"][0]["key"]
    unit["blocks"] = [
        {
            "kind": "text",
            "title": f"Topic {index}",
            "sources": [source],
            "paragraphs": [f"The case uses value {index}."],
        }
        for index in range(8)
    ]
    parsed = StudyContent.model_validate(content)
    before = structure_revision(parsed, None, None, None)
    assert ("flat_sections", f"study/{unit['key']}") in flags(content)
    unit["blocks"][1]["level"] = 2
    nested = StudyContent.model_validate(content)
    assert ("flat_sections", f"study/{unit['key']}") not in flags(content)
    assert structure_revision(nested, None, None, None) != before
    mapped = course_map(nested, None, None, None)["study"]["units"][0]
    assert mapped["headings"][1] == {"title": "Topic 1", "level": 2}
    unit["blocks"] = unit["blocks"][:3]
    for block in unit["blocks"]:
        block["level"] = 1
    assert ("flat_sections", f"study/{unit['key']}") not in flags(content)


def test_flags_teaching_and_practice_repeated_across_units() -> None:
    # Given one passage taught in two units and one question copied into another unit.
    content = study()
    first, second = content["units"][0], content["units"][3]
    for unit in (first, second):
        unit["blocks"].append(
            {"kind": "text", "title": "Relaxation", "sources": [], "paragraphs": [PASSAGE]}
        )
        unit["blocks"][-1]["sources"] = [unit["sources"][0]["key"]]
    question = copy.deepcopy(second["questions"][0])
    question["key"] = "copied"
    question["objective"] = first["questions"][0]["objective"]
    question["sources"] = [first["sources"][0]["key"]]
    for block in question["blocks"]:
        block["sources"] = [first["sources"][0]["key"]]
    first["questions"].append(question)
    # When the structure is checked, both repetitions point at the first place they occur.
    found = flags(content)
    assert ("near_duplicate_passage", "study/graphs") in found
    assert ("near_duplicate_practice", "study/graphs") in found


def test_flags_exercises_concepts_and_lectures_that_do_not_link_their_teaching() -> None:
    # Given exercises that name no passage or only a unit, and a set that runs against the
    # unit order, a cheatsheet concept without a unit and a lecture no unit links.
    content, sheets = study(), exercises()
    later = copy.deepcopy(sheets["sets"][0])
    later["key"], later["title"] = "sheet-2", "Sheet 2"
    for exercise in later["exercises"]:
        exercise["key"] += "-2"
        exercise["prerequisites"] = [{"unit": "graphs", "explanation": "Graphs first."}]
    sheets["sets"].append(later)
    concept = Concept.model_construct(key="relaxation", title="Relaxation", units=(), details=())
    exam = ExamContent.model_construct(concepts=(concept,), topics=(), patterns=(), links=())
    lectures = LectureContent.model_validate_json(
        (FIXTURES / "course_app/lectures.json").read_bytes()
    )
    found = flags(content, sheets, exam=exam, lectures=lectures)
    # Then each missing link and the order clash is named where it can be fixed.
    assert ("unlinked_exercise", "exercises/sheet-1/sample-minimum-proof") in found
    assert ("unlinked_exercise", "exercises/sheet-1/sample-relaxation") in found
    assert ("order_mismatch", "exercises") in found
    assert ("unlinked_concept", "exam") in found
    assert ("unlinked_lecture", "lectures") in found


def test_course_map_and_revision_follow_the_outline_not_the_wording() -> None:
    # Given the course and its exercises.
    content, sheets = study(), exercises()
    revision = structure_revision(
        StudyContent.model_validate(content), ExerciseContent.model_validate(sheets), None, None
    )
    mapped = course_map(
        StudyContent.model_validate(content), ExerciseContent.model_validate(sheets), None, None
    )
    # Then the map lists both workspaces and which exercises need each unit.
    assert mapped["workspaces"] == ["study", "exercises"] and mapped["revision"] == revision
    weighted = next(u for u in mapped["study"]["units"] if u["item"] == "study/weighted")
    assert weighted["exercises"] == ["exercises/sheet-1/sample-relaxation"]
    assert weighted["defines"] == ["tentative distance"]
    # When a summary is reworded the revision stays; when units swap places it changes.
    content["units"][0]["summary"] += " Revised."
    reworded = structure_revision(
        StudyContent.model_validate(content), ExerciseContent.model_validate(sheets), None, None
    )
    content["units"][:2] = content["units"][1::-1]
    reordered = structure_revision(
        StudyContent.model_validate(content), ExerciseContent.model_validate(sheets), None, None
    )
    assert reworded == revision and reordered != revision
