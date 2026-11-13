import json
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.course.checks.report import arithmetic_errors, quality_flags
from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.study import StudyContent

FIXTURES = Path(__file__).parents[1] / "fixtures"


def study() -> dict:
    return json.loads((FIXTURES / "course_app/content.json").read_bytes())


def exercises() -> dict:
    return json.loads((FIXTURES / "exercises.json").read_bytes())


def test_walkthrough_quality_signals_and_visibility_boundaries() -> None:
    catalogue = json.loads((files("tum_mcp") / "bundled/exemplars/blocks.json").read_bytes())
    value = study()
    unit = value["units"][0]
    source = unit["sources"][0]["key"]
    walk = deepcopy(catalogue["walkthrough-tree"])
    walk.update(key="trace", sources=[source])
    walk["steps"] = [
        {
            "action": "Start.",
            "why": r"Use \(A\).",
            "visible_nodes": ["a"],
            "node_values": {"a": "1"},
        },
        {"action": "Next.", "why": "use $A$.", "visible_nodes": ["a", "b"]},
        {"action": "Finish.", "why": r"USE \[A\].", "visible_nodes": ["b"]},
    ]
    diagram = deepcopy(catalogue["diagram-tree"])
    diagram.update(key="input", sources=[source])
    trace = {
        "kind": "table",
        "key": "trace-table",
        "sources": [source],
        "caption": "Search trace",
        "columns": ["Step number", "Frontier state"],
        "rows": [["1", "A"], ["2", "B"], ["3", "C"]],
    }
    unit["blocks"] = [diagram, walk, trace]
    flags = quality_flags(StudyContent.model_validate(value), None)
    relevant = [
        f
        for f in flags
        if f["flag"]
        in {
            "untitled_opening",
            "duplicate_stage",
            "trace_as_table",
            "repeated_step_reason",
            "dropped_node_value",
        }
    ]
    assert [f["flag"] for f in relevant].count("dropped_node_value") == 1
    assert {f["flag"] for f in relevant} == {
        "untitled_opening",
        "duplicate_stage",
        "trace_as_table",
        "repeated_step_reason",
        "dropped_node_value",
    }
    assert next(f["item"] for f in relevant if f["flag"] == "dropped_node_value") == (
        f"{unit['key']}/trace"
    )


def test_walkthrough_variant_is_checked_as_a_separate_run() -> None:
    catalogue = json.loads((files("tum_mcp") / "bundled/exemplars/blocks.json").read_bytes())
    value = study()
    unit = value["units"][0]
    walk = deepcopy(catalogue["walkthrough-tree"])
    walk.update(key="trace", sources=[unit["sources"][0]["key"]])
    walk["label"] = "Primary"
    walk["contrast"] = "The variant starts with a different move."
    walk["variant"] = {
        "label": "Variant",
        "steps": [
            {"action": "Start.", "why": "Same reason.", "node_values": {"a": "1"}},
            {"action": "Expand.", "why": "Same reason."},
            {"action": "Finish.", "why": "Same reason."},
        ],
    }
    unit["blocks"].append(walk)
    flags = quality_flags(StudyContent.model_validate(value), None)
    found = [f["flag"] for f in flags if f["item"] == f"{unit['key']}/trace"]
    assert found.count("repeated_step_reason") == 1
    assert found.count("dropped_node_value") == 1


@pytest.mark.parametrize("show_all", ["hidden", "default", "variant"])
def test_graph_stage_nodes_must_be_shown_in_a_step(show_all: str) -> None:
    catalogue = json.loads((files("tum_mcp") / "bundled/exemplars/blocks.json").read_bytes())
    value = study()
    unit = value["units"][0]
    walk = deepcopy(catalogue["walkthrough-tree"])
    walk.update(key="trace", sources=[unit["sources"][0]["key"]])
    walk["stage"]["nodes"].append({"key": "c", "label": "C"})
    walk["stage"]["edges"].append({"start": "b", "end": "c", "directed": True})
    walk["steps"] = [
        {"action": "Start.", "why": "Begin at A.", "visible_nodes": ["a"]},
        {"action": "Cut off.", "why": "B reaches the limit.", "visible_nodes": ["a", "b"]},
    ]
    if show_all == "default":
        walk["steps"][-1].pop("visible_nodes")
    if show_all == "variant":
        walk.update(label="Primary", contrast="The variant reveals the cut-off branch.")
        walk["variant"] = {
            "label": "Variant",
            "steps": [
                {"action": "Start at A.", "why": "A is initial.", "visible_nodes": ["a"]},
                {"action": "Reveal C.", "why": "C is cut off.", "visible_nodes": ["a", "b", "c"]},
            ],
        }
    unit["blocks"] = [walk]
    flags = quality_flags(StudyContent.model_validate(value), None)
    hidden = [flag for flag in flags if flag["flag"] == "never_shown_nodes"]
    assert bool(hidden) is (show_all == "hidden")
    if hidden:
        from tum_mcp.course.review.models import INVARIANT_FLAGS

        assert "never_shown_nodes" in INVARIANT_FLAGS
        assert hidden[0]["item"] == f"{unit['key']}/trace"


def test_repeated_step_reasons_hold_readiness_without_a_ruling() -> None:
    from tum_mcp.course.review.models import INVARIANT_FLAGS, RULED_FLAGS

    assert INVARIANT_FLAGS["repeated_step_reason"] == "intuition"
    assert "repeated_step_reason" not in RULED_FLAGS


@pytest.mark.parametrize(
    "reasons, flagged",
    [
        (["B is a leaf.", "C is a leaf.", "D is a leaf."], True),
        (
            ["Tile 1 moves to its goal.", "Tile 2 moves to its goal.", "Tile 3 moves to its goal."],
            True,
        ),
        (["B is a leaf.", "C is a leaf."], False),
        (
            [
                "Tile 1: |2-0| + |1-2| = 3.",
                "Tile 2: |1-0| + |0-0| = 1.",
                "Tile 3: |1-2| + |0-2| = 3.",
            ],
            False,
        ),
    ],
)
def test_repeated_reason_threshold_keeps_distinct_working(
    reasons: list[str], flagged: bool
) -> None:
    catalogue = json.loads((files("tum_mcp") / "bundled/exemplars/blocks.json").read_bytes())
    value = study()
    unit = value["units"][0]
    walk = deepcopy(catalogue["walkthrough-tree"])
    walk.update(key="trace", sources=[unit["sources"][0]["key"]])
    walk["steps"] = [{"action": "Expand.", "why": why} for why in reasons]
    unit["blocks"] = [walk]
    flags = quality_flags(StudyContent.model_validate(value), None)
    assert any(flag["flag"] == "repeated_step_reason" for flag in flags) is flagged


def test_trace_table_is_not_flagged_in_question_context() -> None:
    value = study()
    unit = value["units"][0]
    source = unit["sources"][0]["key"]
    unit["questions"][0]["blocks"] = [
        {
            "kind": "table",
            "sources": [source],
            "caption": "Trace",
            "columns": ["Iteration", "Queue"],
            "rows": [["1", "A"], ["2", "B"], ["3", "C"]],
        }
    ]
    assert "trace_as_table" not in {
        f["flag"] for f in quality_flags(StudyContent.model_validate(value), None)
    }


@pytest.mark.parametrize("verb", ["points", "marks", "refers"])
def test_meta_reference_includes_indirect_lecture_verbs(verb: str) -> None:
    value = study()
    value["units"][0]["blocks"][0]["paragraphs"] = [f"The lecture {verb} to this case."]
    assert "meta_reference" in {
        f["flag"] for f in quality_flags(StudyContent.model_validate(value), None)
    }


def test_a_graph_walkthrough_cannot_change_only_its_text() -> None:
    from importlib.resources import files

    value = json.loads((files("tum_mcp") / "bundled/course_app/example/content.json").read_bytes())
    unit = value["units"][0]
    graph = next(b for b in unit["blocks"] if b.get("key") == "walkthrough-graph")
    graph.pop("variant", None)
    graph.pop("label", None)
    graph.pop("contrast", None)
    for step in graph["steps"]:
        for mark in ("active", "frontier", "visited", "edges"):
            step.pop(mark, None)
    content = StudyContent.model_validate(value)
    assert any(flag["flag"] == "static_walkthrough" for flag in quality_flags(content, None))

    graph["steps"][0]["active"] = [graph["stage"]["nodes"][0]["key"]]
    graph["steps"][1]["active"] = [graph["stage"]["nodes"][1]["key"]]
    assert not any(
        flag["flag"] == "static_walkthrough"
        for flag in quality_flags(StudyContent.model_validate(value), None)
    )


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
    # A table repeats givens already stated in the prompt.
    question["prompt"] = "The cost is 6. Which action should the agent choose?"
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
    # The same applies to an exercise's guide and statement.
    guided = exercises()
    guided["sets"][0]["exercises"][0]["steps"][0]["explanation"] = (
        "The lecture checks a generated goal before inserting it."
    )
    narrated = quality_flags(None, ExerciseContent.model_validate(guided))
    assert "meta_reference" in {flag["flag"] for flag in narrated}
    guided = exercises()
    exercise = guided["sets"][0]["exercises"][0]
    exercise["statement"][0]["paragraphs"] = ["The lecture gives the following problem."]
    assert "meta_reference" in {
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


@pytest.mark.parametrize(
    "prompt, repeats",
    [
        ("Which action does the program return?", False),
        ("At B the status is Dirty. Which action does the program return?", True),
        ("At A the status is Dirty. Which action does the program return?", False),
    ],
)
def test_context_repetition_depends_on_givens_not_the_number_of_rows(
    prompt: str, repeats: bool
) -> None:
    content = study()
    unit = content["units"][0]
    question = unit["questions"][0]
    question["prompt"] = prompt
    question["blocks"] = [
        {
            "kind": "table",
            "sources": [unit["sources"][0]["key"]],
            "caption": "Current percept",
            "columns": ["Location", "Status"],
            "rows": [["B", "Dirty"]],
        }
    ]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert (
        any(
            flag["flag"] == "restated_context"
            and flag["item"] == f"{unit['key']}/{question['key']}"
            for flag in flags
        )
        is repeats
    )


def test_a_case_sentence_in_a_table_and_shared_option_feedback_are_flagged() -> None:
    # A trial's templated questions put each case sentence in a one-row table and gave every
    # wrong option the same feedback.
    content = study()
    unit = content["units"][0]
    question = unit["questions"][0]
    item = f"{unit['key']}/{question['key']}"
    case = "A chess program imitates one player's moves and mistakes; only similarity counts."
    question["blocks"] = [
        {
            "kind": "table",
            "sources": [unit["sources"][0]["key"]],
            "caption": "Use these conditions.",
            "columns": ["Feature", "Details"],
            "rows": [["System", case]],
        }
    ]
    for option in question["options"]:
        if option["key"] != question["correct"]:
            option["feedback"] = "Recheck the relevant condition. Outward behaviour is judged."
    flags = {
        (flag["flag"], flag["item"])
        for flag in quality_flags(StudyContent.model_validate(content), None)
    }
    assert ("text_only_question", item) in flags
    assert ("repeated_feedback", item) in flags

    question["blocks"][0]["rows"] = [["B", "Dirty"]]
    question["options"] = study()["units"][0]["questions"][0]["options"]
    wrong = next(o for o in question["options"] if o["key"] != question["correct"])
    wrong["feedback"] = f"Recheck the condition. {question['explanation']}"
    flags = {
        (flag["flag"], flag["item"])
        for flag in quality_flags(StudyContent.model_validate(content), None)
    }
    assert ("repeated_feedback", item) in flags

    question["options"] = study()["units"][0]["questions"][0]["options"]
    flags = {
        (flag["flag"], flag["item"])
        for flag in quality_flags(StudyContent.model_validate(content), None)
    }
    assert ("text_only_question", item) not in flags
    assert ("repeated_feedback", item) not in flags


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
    # A sum worked in plain digits is an equation too; the same sum in LaTeX passes.
    content["units"][0]["blocks"][0]["paragraphs"] = ["The path costs 3+1+5=9 in total."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key in {f["item"] for f in flags if f["flag"] == "plain_math"}
    content["units"][0]["blocks"][0]["paragraphs"] = [r"The path costs \(3+1+5=9\) in total."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key not in {f["item"] for f in flags if f["flag"] == "plain_math"}
    # A paper size is not a subscripted variable; setting it in LaTeX made it italic.
    content["units"][0]["blocks"][0]["paragraphs"] = ["Bring one handwritten A4 sheet."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key not in {f["item"] for f in flags if f["flag"] == "plain_math"}
    # Forms a pilot's reviewers found: sets, predicates, middle-dot products, split formulas.
    for typed in ("X={1,2}", "Resolve with P(a).", "Use 0.6·200.", r"Then \(C_2\)=3."):
        content["units"][0]["blocks"][0]["paragraphs"] = [typed]
        flags = quality_flags(StudyContent.model_validate(content), None)
        assert key in {f["item"] for f in flags if f["flag"] == "plain_math"}, typed
    content["units"][0]["blocks"][0]["paragraphs"] = [r"Compare \(x\) and \(y\)."]
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


def test_a_summary_that_repeats_an_objective_is_flagged() -> None:
    # QC's Bloch-sphere unit shipped with its only objective copied as the summary.
    content = study()
    unit = content["units"][0]
    unit["summary"] = unit["objectives"][0]["text"].upper().rstrip(".")
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert ("summary_repeats_objective", unit["key"]) in {(f["flag"], f["item"]) for f in flags}
    unit["summary"] = "Which direction does a qubit point in, and what does its phase change?"
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert ("summary_repeats_objective", unit["key"]) not in {(f["flag"], f["item"]) for f in flags}


def test_a_graph_listed_as_edge_rows_is_flagged() -> None:
    content = study()
    unit = content["units"][0]
    sources = unit["blocks"][0]["sources"]
    unit["blocks"].append(
        {
            "kind": "table",
            "key": "edges",
            "sources": sources,
            "caption": "Road costs.",
            "columns": ["From", "To", "Cost"],
            "rows": [["A", "B", "2"], ["A", "C", "3"]],
        }
    )
    unit["blocks"].append(
        {
            "kind": "table",
            "key": "schedule",
            "sources": sources,
            "caption": "Weekly sessions.",
            "columns": ["Session", "Start", "End"],
            "rows": [["Lecture", "10:00", "11:30"]],
        }
    )
    flags = {
        (f["flag"], f["item"]) for f in quality_flags(StudyContent.model_validate(content), None)
    }
    assert ("graph_as_table", f"{unit['key']}#{len(unit['blocks']) - 2}") in flags
    assert ("graph_as_table", f"{unit['key']}#{len(unit['blocks']) - 1}") not in flags


def test_a_table_walkthrough_showing_every_result_up_front_is_flagged() -> None:
    content = study()
    unit = content["units"][0]
    rows = [[str(tile), str(distance)] for tile, distance in enumerate([3, 1, 2, 2, 2, 3, 3, 2], 1)]
    walk = {
        "kind": "walkthrough",
        "key": "tiles",
        "sources": unit["blocks"][0]["sources"],
        "stage": {
            "kind": "table",
            "caption": "Tile distances.",
            "columns": ["Tile", "Distance"],
            "rows": rows,
        },
        "steps": [
            {"action": "Measure tile 1.", "why": "Two rows and one column away.", "cells": ["1:1"]},
            {"action": "Add the distances.", "why": "The blank is not counted."},
        ],
    }
    unit["blocks"].append(walk)
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert "unstepped_table" in {f["flag"] for f in flags}
    walk["steps"] = [
        {
            "action": f"Measure tile {n}.",
            "why": "Rows plus columns away.",
            "shown": n,
            "cells": [f"{n}:1"],
        }
        for n in range(1, 9)
    ]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert "unstepped_table" not in {f["flag"] for f in flags}


def test_two_walkthroughs_over_the_same_drawing_are_flagged() -> None:
    from importlib.resources import files

    example = json.loads(
        (files("tum_mcp") / "bundled/course_app/example/content.json").read_bytes()
    )
    content = study()
    unit = content["units"][0]
    walk = next(b for b in example["units"][0]["blocks"] if b.get("key") == "walkthrough-graph")
    walk["sources"] = unit["blocks"][0]["sources"]
    unit["blocks"].append(walk)
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert "repeated_example" not in {f["flag"] for f in flags}
    unit["blocks"].append(walk | {"key": "replayed", "title": "Compare your trace"})
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert ("repeated_example", unit["key"]) in {(f["flag"], f["item"]) for f in flags}


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


def test_mathematics_read_aloud_in_words_is_flagged_but_names_are_not() -> None:
    content = study()
    key = content["units"][0]["key"]
    content["units"][0]["blocks"][0]["paragraphs"] = ["Reflect at angle theta over two."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key in {f["item"] for f in flags if f["flag"] == "plain_math"}
    content["units"][0]["blocks"][0]["paragraphs"] = ["A beta distribution spreads over two days."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key not in {f["item"] for f in flags if f["flag"] == "plain_math"}


def test_a_derivation_line_listing_several_statements_is_flagged() -> None:
    content = study()
    unit = content["units"][0]
    sources = unit["blocks"][0]["sources"]
    line = {"latex": r"N=4,\quad M=1", "reason": "The givens."}
    unit["blocks"].append(
        {"kind": "derivation", "title": "Work", "sources": sources, "groups": [{"lines": [line]}]}
    )
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert unit["key"] in {f["item"] for f in flags if f["flag"] == "listed_derivation_line"}
    line["latex"] = r"N=4"
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert unit["key"] not in {f["item"] for f in flags if f["flag"] == "listed_derivation_line"}
    assert unit["key"] not in {f["item"] for f in flags if f["flag"] == "unaligned_line"}
    line["latex"] = r"\tfrac12(I+Z)"
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert unit["key"] in {f["item"] for f in flags if f["flag"] == "unaligned_line"}


def test_an_action_hidden_in_a_noun_is_flagged() -> None:
    content = study()
    key = content["units"][0]["key"]
    content["units"][0]["blocks"][0]["paragraphs"] = ["We perform the computation of the trace."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key in {f["item"] for f in flags if f["flag"] == "nominalisation"}
    content["units"][0]["blocks"][0]["paragraphs"] = ["We compute the trace."]
    flags = quality_flags(StudyContent.model_validate(content), None)
    assert key not in {f["item"] for f in flags if f["flag"] == "nominalisation"}


def test_an_exercise_statement_that_frames_instead_of_giving_is_flagged() -> None:
    payload = exercises()
    exercise = payload["sets"][0]["exercises"][0]
    source = exercise["sources"][0]["key"]
    framing = {
        "kind": "text",
        "sources": [source],
        "paragraphs": [
            "This exercise should refresh your knowledge of graphs.",
            "The section explains graphs.",
        ],
    }
    exercise["statement"] = [framing, *exercise["statement"]]
    flags = quality_flags(
        StudyContent.model_validate(study()), ExerciseContent.model_validate(payload)
    )
    assert exercise["key"] in {f["item"] for f in flags if f["flag"] == "statement_framing"}
    assert exercise["key"] in {f["item"] for f in flags if f["flag"] == "meta_reference"}


def test_traces_results_and_snapshots_must_show_their_steps() -> None:
    # Given a lesson whose objective asks students to trace, with only a finished table.
    content = study()
    unit = content["units"][0]
    unit["objectives"][0]["text"] = "Trace a degree count over the edge list."
    sources = unit["blocks"][0]["sources"]
    flags = lambda: {  # noqa: E731
        flag["flag"] for flag in quality_flags(StudyContent.model_validate(content), None)
    }
    assert "static_trace" in flags() and "untraced_procedure" not in flags()
    # When the table becomes a walkthrough with a reason per step, the trace is taught.
    table = next(b for b in unit["blocks"] if b["kind"] == "table")
    walk = {
        "kind": "walkthrough",
        "sources": sources,
        "stage": {k: table[k] for k in ("kind", "columns", "rows", "caption")},
        "steps": [
            {"action": "Fill the first row.", "why": "It has no dependency.", "shown": 1},
            {"action": "Fill the rest.", "why": "Each row reuses the first.", "shown": 2},
        ],
    }
    unit["blocks"][unit["blocks"].index(table)] = walk
    assert not {"static_trace", "untraced_procedure"} & flags()
    # A computed result in prose needs working in its section; a given does not.
    unit["blocks"][0]["paragraphs"] = [r"With \(n = 4\) vertices, \(2 \cdot 3 = 6\) ends."]
    assert "unworked_result" in flags()
    unit["blocks"].insert(
        1,
        {
            "kind": "derivation",
            "sources": sources,
            "groups": [{"lines": [{"latex": r"2 \cdot 3 = 6", "reason": "Two ends per edge."}]}],
        },
    )
    assert "unworked_result" not in flags()
    # One frame of a traversal is a snapshot of a process.
    unit["blocks"].append(
        {
            "kind": "diagram",
            "title": "Midway",
            "sources": sources,
            "description": "Two vertices, one reached.",
            "nodes": [
                {"key": "a", "label": "A", "row": 0, "col": 0},
                {"key": "b", "label": "B", "row": 0, "col": 1},
            ],
            "edges": [{"start": "a", "end": "b"}],
            "frames": [{"caption": "A is done.", "visited": ["a"], "frontier": ["b"]}],
        }
    )
    assert "single_frame_diagram" in flags()


def test_bookkeeping_in_set_summaries_and_exam_labels_is_flagged() -> None:
    from importlib.resources import files

    from tum_mcp.course.content.exam import ExamContent
    from tum_mcp.course.content.exam_data import meta_flags

    payload = exercises()
    payload["sets"][0]["summary"] = "User-provided sheet with the official solution."
    flags = quality_flags(None, ExerciseContent.model_validate(payload))
    first = payload["sets"][0]["exercises"][0]["key"]
    assert ("meta_reference", first) in {(flag["flag"], flag["item"]) for flag in flags}
    payload["sets"][0]["summary"] = "The Moodle folder is marked subject to change."
    flags = quality_flags(None, ExerciseContent.model_validate(payload))
    assert ("meta_reference", first) in {(flag["flag"], flag["item"]) for flag in flags}
    # Provenance inside a statement is narration too.
    payload["sets"][0]["summary"] = None
    statement = next(
        b for b in payload["sets"][0]["exercises"][0]["statement"] if b["kind"] == "text"
    )
    statement["points"] = ["Assume no new dirt, as in the official solution."]
    flags = quality_flags(None, ExerciseContent.model_validate(payload))
    assert ("meta_reference", first) in {(flag["flag"], flag["item"]) for flag in flags}
    exam = json.loads((files("tum_mcp") / "bundled/course_app/example/exam.json").read_bytes())
    assert meta_flags(ExamContent.model_validate(exam)) == []
    exam["sittings"][0]["label"] += " (user-provided)"
    flagged = meta_flags(ExamContent.model_validate(exam))
    assert flagged and all(flag["item"].startswith("exam/pattern/") for flag in flagged)


def test_a_cited_page_past_the_end_of_its_source_is_flagged(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from tum_mcp.course.checks.report import citation_flags
    from tum_mcp.course.sources import text

    # Given a current source whose read text has 12 pages.
    source = SimpleNamespace(
        status="current", sha256="a" * 64, resource=SimpleNamespace(key="slides")
    )
    monkeypatch.setattr(text, "cached_record", lambda root, sha: SimpleNamespace(pages=[None] * 12))
    state = SimpleNamespace(resources=[source])
    block = {"kind": "text", "sources": ["slides"], "pages": "11-12"}
    assert citation_flags(tmp_path, state, {"graphs": {"blocks": [block]}}) == []
    block["pages"] = "12-14"
    assert [
        flag["item"] for flag in citation_flags(tmp_path, state, {"graphs": {"blocks": [block]}})
    ] == ["graphs"]


def test_a_linked_cheatsheet_fact_no_card_asks_for_is_flagged() -> None:
    from importlib.resources import files

    from tum_mcp.course.content.exam import ExamContent
    from tum_mcp.course.content.exam_data import retrieval_flags

    folder = files("tum_mcp") / "bundled/course_app/example"
    raw = json.loads((folder / "exam.json").read_bytes())
    study = json.loads((folder / "content.json").read_bytes())
    entry = next(c for c in raw["concepts"] if c["kind"] == "definition")
    entry["units"] = [study["units"][0]["key"]]
    exam = ExamContent.model_validate(raw)
    concept = next(c for c in exam.concepts if c.kind == "definition")
    flagged = {flag["item"] for flag in retrieval_flags(exam, StudyContent.model_validate(study))}
    assert f"concept:{concept.key}" in flagged
    card = study["units"][0]["flashcards"][0]
    card["front"] = f"What is a {concept.title}?"
    asked = {flag["item"] for flag in retrieval_flags(exam, StudyContent.model_validate(study))}
    assert f"concept:{concept.key}" not in asked


def test_a_section_cannot_run_three_paragraphs_even_across_untitled_blocks() -> None:
    # Trial units split a six-paragraph section into short untitled blocks to pass length checks.
    content = study()
    unit = content["units"][0]
    source = unit["blocks"][0]["sources"]
    lead = {"kind": "text", "title": "Choosing a method", "sources": source}
    blocks = [
        lead | {"paragraphs": ["Pick the method from what is given.", "Each method needs input."]},
        {"kind": "text", "sources": source, "paragraphs": ["Search needs a goal test."]},
    ]
    unit["blocks"] = blocks + unit["blocks"]

    def runs() -> list[str]:
        found = quality_flags(StudyContent.model_validate(content), None)
        return [flag["item"] for flag in found if flag["flag"] == "prose_run"]

    assert runs() == [f"{unit['key']}#0"]
    blocks[1]["points"] = ["Inference needs premises."]
    blocks[1]["paragraphs"] = []
    unit["blocks"] = blocks + unit["blocks"][2:]
    assert runs() == []


def test_a_worked_case_told_as_prose_is_raised_and_an_example_block_is_valid() -> None:
    content = study()
    unit = content["units"][0]
    source = unit["blocks"][0]["sources"]
    case = "Suppose a test is positive with probability 0.8 given the disease."
    unit["blocks"].append({"kind": "text", "sources": source, "paragraphs": [case]})
    found = quality_flags(StudyContent.model_validate(content), None)
    assert any(flag["flag"] == "example_in_prose" for flag in found)

    unit["blocks"][-1] = {
        "kind": "example",
        "sources": source,
        "given": ["\\(P(+ \\mid d) = 0.8\\)"],
        "steps": ["Weigh by the prior."],
        "result": "The posterior.",
    }
    found = quality_flags(StudyContent.model_validate(content), None)
    assert not any(flag["flag"] == "example_in_prose" for flag in found)
    pitfall = {"kind": "callout", "sources": source, "tone": "pitfall", "text": "Mixed."}
    unit["blocks"].append(pitfall)
    with pytest.raises(ValidationError, match="situation, wrong, right and why"):
        StudyContent.model_validate(content)


def test_item_writing_cues_and_placeholder_tables_are_raised() -> None:
    # A trial's questions all sat on 'Case / Feature / Information' tables; one key ran long.
    content = study()
    unit = content["units"][0]
    question = unit["questions"][0]
    source = unit["blocks"][0]["sources"]
    wrapper = {
        "kind": "table",
        "sources": source,
        "caption": "Case",
        "columns": ["Feature", "Information"],
        "rows": [["Observation", "A chatbot improved twice."]],
    }
    question["blocks"] = [wrapper]

    item = f"{unit['key']}/{question['key']}"

    def raised() -> set[str]:
        found = quality_flags(StudyContent.model_validate(content), None)
        return {flag["flag"] for flag in found if flag["item"] == item}

    assert "generic_table" in raised()
    # A pilot lesson used 'Case / What it illustrates' three times beside its own prose.
    wrapper.update(caption="A time-sensitive choice", columns=["Case", "What it illustrates"])
    assert "generic_table" in raised()
    wrapper.update(caption="Readings", columns=["Variable", "Value"])
    assert "generic_table" not in raised()
    wrong = next(o for o in question["options"] if o["key"] != question["correct"])
    wrong["text"] = "All of the above"
    key = next(o for o in question["options"] if o["key"] == question["correct"])
    key["text"] += " because the condition holds for every reachable state of the search"
    assert {"all_of_above", "key_longest"} <= raised()


def test_a_sentence_copied_from_an_exemplar_is_ruled_on() -> None:
    from importlib.resources import files

    folder = files("tum_mcp") / "bundled/exemplars"
    exemplar = StudyContent.model_validate_json((folder / "study.json").read_bytes())
    copied = [f for f in quality_flags(exemplar, None) if f["flag"] == "exemplar_copy"]
    assert "bfs" in {f["item"] for f in copied}
    own = StudyContent.model_validate(study())
    assert not [f for f in quality_flags(own, None) if f["flag"] == "exemplar_copy"]


def test_a_part_heading_that_repeats_its_own_text_is_flagged() -> None:
    # A pilot sheet titled a part "1. Playing football" above the paragraph "Playing football".
    payload = exercises()
    exercise = payload["sets"][0]["exercises"][0]
    block = next(b for b in exercise["statement"] if b["kind"] == "text")
    block.update(title="1. Playing football", paragraphs=["Playing football"])

    def flagged() -> bool:
        found = quality_flags(None, ExerciseContent.model_validate(payload))
        return any(f["flag"] == "repeated_title" for f in found if f["item"] == exercise["key"])

    assert flagged()
    block["title"] = "1."
    assert not flagged()


def test_a_workflow_step_that_computes_shows_its_formula() -> None:
    # A pilot's decision pattern said "multiply utilities by probabilities" with no formula.
    from importlib.resources import files

    from tum_mcp.course.content.exam import ExamContent
    from tum_mcp.course.content.exam_data import exam_item_flags

    exam = json.loads((files("tum_mcp") / "bundled/course_app/example/exam.json").read_bytes())
    pattern = exam["patterns"][0]
    step = pattern["workflow"][-1]
    step.pop("cases", None)
    step["do"] = "Compute the expected utility of each action."
    step["apply"] = {"text": "Multiply each utility by its probability and sum."}

    def flagged() -> bool:
        found = exam_item_flags(ExamContent.model_validate(exam))
        item = f"exam/pattern/{pattern['key']}"
        return any(f["flag"] == "bare_workflow" and f["item"] == item for f in found)

    assert flagged()
    step["apply"] = {"text": r"Use \(EU(a) = \sum_s P(s \mid a)\,U(s)\)."}
    assert not flagged()


def test_the_cheatsheet_needs_a_semester_map_with_every_idea_linked() -> None:
    # Three pilot exams drew no links, so the app showed no semester map at all.
    from importlib.resources import files

    from tum_mcp.course.content.exam import ExamContent
    from tum_mcp.course.content.exam_data import exam_item_flags

    exam = json.loads((files("tum_mcp") / "bundled/course_app/example/exam.json").read_bytes())

    def flagged() -> bool:
        found = exam_item_flags(ExamContent.model_validate(exam))
        return any(f["flag"] == "unlinked_map" and f["item"] == "exam/sheet" for f in found)

    assert not flagged()
    lone = exam["concepts"][0] | {"key": "lone-idea", "basis": "untested_core", "on_map": True}
    exam["concepts"].append(lone)
    assert flagged()
    lone["on_map"] = False
    assert not flagged()


def test_a_word_in_math_mode_is_flagged_and_text_or_a_matrix_passes() -> None:
    # A pilot's exam patterns wrote P(A=true) and P(pass real | warning) in math mode.
    content = study()
    key = content["units"][0]["key"]
    block = content["units"][0]["blocks"][0]

    def flagged(paragraph: str) -> bool:
        block["paragraphs"] = [paragraph]
        found = quality_flags(StudyContent.model_validate(content), None)
        return any(f["flag"] == "math_word" and f["item"] == key for f in found)

    assert flagged(r"Here \(P(A=true)\) holds.")
    assert not flagged(r"Here \(P(A=\mathrm{true})\) holds.")
    assert not flagged(r"Here \(\begin{pmatrix}1 & 0\end{pmatrix}\) is a row.")
