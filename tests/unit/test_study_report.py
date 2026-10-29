import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.study_content import StudyContent
from tum_mcp.study_report import arithmetic_errors, quality_flags

FIXTURES = Path(__file__).parents[1] / "fixtures"


def study() -> dict:
    return json.loads((FIXTURES / "course_app/content.json").read_bytes())


def exercises() -> dict:
    return json.loads((FIXTURES / "exercises.json").read_bytes())


def test_arithmetic_in_prose_is_recomputed_outside_math_and_code() -> None:
    # The MDP return that a generated lesson once stated as 4.5.
    assert arithmetic_errors("B returns 1 + 0.5 × 6 = 4.5 in total.") == [
        "1 + 0.5 × 6 = 4.5 (computes to 4)"
    ]
    assert arithmetic_errors("B returns 1 + 0.5 × 6 = 4, less than 5.") == []
    assert arithmetic_errors(r"Inside math \(1 + 1 = 3\) and code `2*2 = 5` stay unread.") == []
    assert arithmetic_errors("Lecture 2 = slides 1-8 and 200 × 0.8 = 160.") == []
    assert arithmetic_errors("Party: 0.6×(−100)+0.4×500 = 140.") == []
    assert arithmetic_errors("Party: 0.6×(−100)+0.4×500 = 150.") != []


def test_flags_point_at_dense_prose_unanswered_tables_and_large_steps() -> None:
    # Given a lesson paragraph of one long run-on and a step whose table Compare never answers.
    content = study()
    content["units"][0]["blocks"][0]["paragraphs"] = ["Word " * 130]
    payload = exercises()
    step = payload["sets"][0]["exercises"][0]["steps"][0]
    step["blocks"] = [
        {
            "kind": "table",
            "title": "Cases",
            "sources": [],
            "caption": "Fill in each case",
            "columns": ["Case", "Cost"],
            "rows": [["Via A", "?"], ["Direct", "5"]],
        }
    ]
    source = payload["sets"][0]["exercises"][0]["sources"][0]["key"]
    step["blocks"][0]["sources"] = [source]
    # When the report derives its flags.
    flags = quality_flags(
        StudyContent.model_validate(content), ExerciseContent.model_validate(payload)
    )
    kinds = {(flag["flag"], flag["item"].split("#")[0].split("/")[0]) for flag in flags}
    # Then each finding names its item, and clean content raises none of these flags.
    assert ("dense_paragraph", content["units"][0]["key"]) in kinds
    assert ("unanswered_table", payload["sets"][0]["exercises"][0]["key"]) in kinds
    # A released statement pasted as one block, with several parts, is flagged for structure.
    statement = payload["sets"][0]["exercises"][0]["statement"]
    first = next(b for b in statement if b["kind"] == "text")
    first["paragraphs"] = ["Problem 1.1: Trace it. Problem 1.2: Compare it."]
    walls = quality_flags(None, ExerciseContent.model_validate(payload))
    assert "dense_statement" in {flag["flag"] for flag in walls}
    # A question that carries two pictures no longer fits one phone screen.
    question = content["units"][0]["questions"][0]
    picture = next(b for b in content["units"][0]["blocks"] if b["kind"] == "formula")
    question["blocks"] = [picture, picture]
    # A slide number in a title belongs in pages, where the citation opens.
    picture["title"] = "Weighted sum · slides 4–6"
    long = quality_flags(StudyContent.model_validate(content), None)
    found = {(flag["flag"], flag["item"]) for flag in long}
    assert ("long_question", f"{content['units'][0]['key']}/{question['key']}") in found
    assert ("citation_in_title", content["units"][0]["key"]) in found
    # A one-row table beside a question only repeats its prompt.
    question["blocks"] = [
        {
            "kind": "table",
            "title": "The state",
            "sources": picture["sources"],
            "caption": "Given.",
            "columns": ["Quantity", "Value"],
            "rows": [["Cost", "6"]],
        }
    ]
    restated = quality_flags(StudyContent.model_validate(content), None)
    assert "restated_context" in {flag["flag"] for flag in restated}
    # A sentence about the material, not the subject, is flagged for rewriting.
    content["units"][0]["blocks"][0]["paragraphs"] = ["The lecture groups methods by cost."]
    narrated = quality_flags(StudyContent.model_validate(content), None)
    assert "meta_reference" in {flag["flag"] for flag in narrated}
    clean = quality_flags(
        StudyContent.model_validate(study()), ExerciseContent.model_validate(exercises())
    )
    assert not {flag["flag"] for flag in clean} & {
        "dense_paragraph",
        "unanswered_table",
        "arithmetic",
        "long_question",
        "citation_in_title",
        "restated_context",
        "meta_reference",
        "long_section",
        "dense_statement",
    }


def test_terms_definitions_and_question_context_are_checked_by_the_schema() -> None:
    content = study()
    unit = content["units"][0]
    source = unit["sources"][0]["key"]
    unit["blocks"].insert(
        0,
        {
            "kind": "definition",
            "key": "degree",
            "sources": [source],
            "term": "Degree",
            "statement": "The number of edges incident to a vertex.",
        },
    )
    unit["blocks"][1]["paragraphs"].append("Each {{degree}} counts edge ends.")
    parsed = StudyContent.model_validate(content)
    assert parsed.definitions()["Degree"]["block"] == "degree"
    # A marked term with no definition, a repeated block key or a text-only question fails.
    for change in (
        lambda c: c["units"][0]["blocks"][1]["paragraphs"].append("A {{loop}} closes a path."),
        lambda c: c["units"][0]["blocks"][1].update(key="degree"),
        lambda c: c["units"][0]["questions"][0].update(blocks=[c["units"][0]["blocks"][1]]),
    ):
        broken = json.loads(json.dumps(content))
        change(broken)
        with pytest.raises(ValidationError):
            StudyContent.model_validate(broken)


def test_solutions_answer_each_part_once_and_say_each_thing_once() -> None:
    payload = exercises()
    exercise = payload["sets"][0]["exercises"][0]
    exercise["parts"] = ["(a) Compute the cost.", "(b) Explain the update."]
    with pytest.raises(ValidationError, match="one solution answer for each original part"):
        ExerciseContent.model_validate(payload)
    answer = exercise["solution"]["answers"][0]
    exercise["solution"]["answers"] = [answer | {"label": "(a)"}, answer | {"label": "(b)"}]
    ExerciseContent.model_validate(payload)
    step = next(s for s in exercise["steps"] if s.get("check", {}).get("kind") == "self_check")
    step["explanation"] = " ".join(step["check"]["model_answer"][0]["paragraphs"])
    with pytest.raises(ValidationError, match="repeats its model answer"):
        ExerciseContent.model_validate(payload)
