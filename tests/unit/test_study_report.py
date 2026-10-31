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
    assert arithmetic_errors(r"Code `2*2 = 5` stays unread.") == []
    assert arithmetic_errors(r"Continue gives \(1 + 0.5 \times 3 = 2.5\).") == []
    assert arithmetic_errors(r"Continue gives \(1 + 0.5 \times 3 = 3.5\).") != []
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
    content["units"][0]["blocks"][0]["paragraphs"] = ["The lecture gives a bound of n squared."]
    narrated = quality_flags(StudyContent.model_validate(content), None)
    assert "meta_reference" in {flag["flag"] for flag in narrated}
    # The same applies to an exercise's guide, though not to its released statement.
    guided = exercises()
    guided["sets"][0]["exercises"][0]["steps"][0]["explanation"] = (
        "The lecture checks a generated goal before inserting it."
    )
    narrated = quality_flags(None, ExerciseContent.model_validate(guided))
    assert "meta_reference" in {flag["flag"] for flag in narrated}
    guided = exercises()
    exercise = guided["sets"][0]["exercises"][0]
    exercise["statement"][0]["paragraphs"] = ["The lecture gives the following problem."]
    assert "meta_reference" not in {
        flag["flag"] for flag in quality_flags(None, ExerciseContent.model_validate(guided))
    }
    step = next(step for step in exercise["steps"] if step["check"]["kind"] == "self_check")
    step["check"]["model_answer"][0]["paragraphs"] = ["The lecture explains this update."]
    assert "meta_reference" in {
        flag["flag"] for flag in quality_flags(None, ExerciseContent.model_validate(guided))
    }
    # A Compare answer listing several computed results in one sentence asks for working.
    step["check"]["model_answer"][0]["paragraphs"] = [
        r"\(a+b = 5+3i\), \(ab = 10+5i\), \(1/a = (3-4i)/25\) and \(|a| = 5\)."
    ]
    assert "compressed_working" in {
        flag["flag"] for flag in quality_flags(None, ExerciseContent.model_validate(guided))
    }
    clean = quality_flags(
        StudyContent.model_validate(study()), ExerciseContent.model_validate(exercises())
    )
    assert not {flag["flag"] for flag in clean} & {
        "compressed_working",
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


def test_flags_flowing_procedures_and_calculation_chains_in_prose() -> None:
    # Given the value-iteration paragraph a student could not study: three sentences of
    # procedure, and a policy evaluation computed inside a sentence.
    content = study()
    content["units"][0]["blocks"][0]["paragraphs"] = [
        "In the one-state example, continue is initially valued at 1. After the first backup, "
        "the continuation value becomes 2.5, still below stopping at 3. Because the next backup "
        "again returns 3, the value has reached its fixed point.",
        "A policy that always continues has value V = 1 + 0.5V = 2, so it switches to stop.",
    ]
    # When the report derives its flags.
    flags = quality_flags(StudyContent.model_validate(content), None)
    found = {flag["flag"] for flag in flags if flag["item"].startswith(content["units"][0]["key"])}
    # Then both the run-on procedure and the inline calculation chain are flagged.
    assert {"dense_paragraph", "prose_calculation"} <= found


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


def test_mathematics_typed_as_plain_text_is_flagged_and_latex_passes() -> None:
    # Given one lesson that types a discount, a conditional and an equation as plain characters.
    content = study()
    key = content["units"][0]["key"]
    content["units"][0]["blocks"][0]["paragraphs"] = ["With γ = 0.5, P(A|B) gives V = 3."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    # Then the unit is flagged once, and the same sentence in inline LaTeX passes.
    assert key in {f["item"] for f in flags if f["flag"] == "plain_math"}
    content["units"][0]["blocks"][0]["paragraphs"] = [
        r"With \(\gamma = 0.5\), \(P(A \mid B)\) gives \(V = 3\)."
    ]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key not in {f["item"] for f in flags if f["flag"] == "plain_math"}


def test_spelled_out_objects_and_large_inline_matrices_are_flagged() -> None:
    # Given a lesson that describes a matrix in words and puts a 3x3 matrix inside a sentence.
    content = study()
    key = content["units"][0]["key"]
    content["units"][0]["blocks"][0]["paragraphs"] = [
        r"The diagonal matrix with entries \(1, 0\) keeps \(|0\rangle\).",
        r"Here \(\begin{pmatrix}1&0&0\\0&1&0\\0&0&1\end{pmatrix}\) is the identity.",
    ]
    flags = quality_flags(StudyContent.model_validate(content), None)
    found = {f["flag"] for f in flags if f["item"] == key}
    assert {"described_object", "tall_inline_math"} <= found
    # Then showing the matrix itself, a 2x2 inline matrix and a column vector pass.
    content["units"][0]["blocks"][0]["paragraphs"] = [
        r"\(P = \begin{pmatrix}1 & 0\\ 0 & 0\end{pmatrix}\) keeps \(|0\rangle\).",
        r"The state \(\begin{pmatrix}1\\0\\0\end{pmatrix}\) is a basis vector.",
    ]
    flags = quality_flags(StudyContent.model_validate(content), None)
    found = {f["flag"] for f in flags if f["item"] == key}
    assert not {"described_object", "tall_inline_math"} & found


def test_flags_a_flat_outline_a_shared_guide_and_assumption_asides() -> None:
    # Given a five-unit course without groups and a two-part exercise with one guide.
    content = study()
    for unit in content["units"]:
        unit.pop("path", None)
    payload = exercises()
    exercise = payload["sets"][0]["exercises"][0]
    exercise["parts"] = ["(a)", "(b)"]
    answer = exercise["solution"]["answers"][0]
    exercise["solution"]["answers"] = [{**answer, "label": "(a)"}, {**answer, "label": "(b)"}]
    exercise["solution"]["notes"] = [
        {
            "kind": "text",
            "title": "Assumptions and sources",
            "sources": exercise["statement"][0]["sources"],
            "paragraphs": ["Dirt does not return."],
        }
    ]
    # When the report reads them.
    flags = {
        item["flag"]
        for item in quality_flags(
            StudyContent.model_validate(content), ExerciseContent.model_validate(payload)
        )
    }
    # Then each structural gap is named.
    assert {"flat_outline", "shared_guide", "assumption_aside"} <= flags
    grouped = quality_flags(
        StudyContent.model_validate(study()), ExerciseContent.model_validate(exercises())
    )
    assert not {"flat_outline", "shared_guide", "assumption_aside"} & {
        item["flag"] for item in grouped
    }


def test_a_dense_opening_and_a_worked_case_without_its_rule_are_flagged() -> None:
    # Given a unit that opens with three new symbols and a term before any picture.
    content = study()
    unit = content["units"][0]
    key, sources = unit["key"], unit["blocks"][0]["sources"]
    unit["blocks"][0]["paragraphs"] = [
        r"A state uses angles \(\theta\) and \(\varphi\) and a phase \(\gamma\)."
    ]
    unit["blocks"].insert(
        1,
        {
            "kind": "definition",
            "term": "Relative phase",
            "statement": "The angle.",
            "sources": sources,
        },
    )
    found = {
        f["flag"]
        for f in quality_flags(StudyContent.model_validate(content), None)
        if f["item"] == key
    }
    assert "dense_introduction" in found
    # Then the same notation after a concrete picture is not flagged as a dense opening.
    figure = next(
        b for u in study()["units"] for b in u["blocks"] if b["kind"] in {"table", "diagram"}
    )
    unit["blocks"].insert(0, figure | {"sources": sources, "title": "A first case"})
    found = {
        f["flag"]
        for f in quality_flags(StudyContent.model_validate(content), None)
        if f["item"] == key
    }
    assert "dense_introduction" not in found


def test_a_worked_calculation_without_a_general_rule_is_flagged() -> None:
    content = study()
    unit = content["units"][0]
    unit["blocks"] = [b for b in unit["blocks"] if b["kind"] != "formula"]
    unit["blocks"].append(
        {
            "kind": "text",
            "sources": unit["blocks"][0]["sources"],
            "steps": [r"Multiply by the conjugate: \(1/(3+4i) = (3-4i)/25\)."],
        }
    )
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert ("example_without_rule", unit["key"]) in {(f["flag"], f["item"]) for f in flags}


def test_a_symbol_dense_identity_in_a_sentence_is_flagged_and_a_formula_block_is_not() -> None:
    content = study()
    unit = content["units"][0]
    unit["blocks"][0]["paragraphs"] = [
        r"For product states, \((\langle a|\otimes\langle b|)(|c\rangle\otimes|d\rangle)"
        r"=\langle a|c\rangle\langle b|d\rangle\)."
    ]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert ("unexplained_identity", unit["key"]) in {(f["flag"], f["item"]) for f in flags}
    unit["blocks"][0]["paragraphs"] = [r"The first factors give \(\langle 0|1\rangle = 0\)."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert ("unexplained_identity", unit["key"]) not in {(f["flag"], f["item"]) for f in flags}
