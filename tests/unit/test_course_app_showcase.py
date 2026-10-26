from fractions import Fraction
from importlib.resources import files
from pathlib import Path

from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.study_content import StudyContent


def test_distributed_preview_is_one_component_unit_and_one_exercise() -> None:
    example = files("tum_mcp") / "bundled/course_app/example"
    study = StudyContent.model_validate_json((example / "content.json").read_bytes())
    exercises = ExerciseContent.model_validate_json((example / "exercises.json").read_bytes())
    assert len(study.units) == len(exercises.sets) == 1
    unit = study.units[0]
    assert {block.kind for block in unit.blocks} == {
        "text",
        "formula",
        "table",
        "code",
        "diagram",
        "plot",
    }
    assert len(unit.flashcards) == len(unit.questions) == 1
    assert len(exercises.sets[0].exercises) == 1
    exercise = exercises.sets[0].exercises[0]
    assert {step.check.kind for step in exercise.steps} == {
        "numeric",
        "choice",
        "self_check",
        "table",
        "graph",
        "plot",
    }
    assert "not necessarily good examples" in study.introduction
    assert "not necessarily good examples" in exercise.statement[0].paragraphs[0]


def paths(edges, start, end, seen=()):
    if start == end:
        yield 0
    for a, b, cost in edges:
        if a == start and b not in (*seen, start):
            for suffix in paths(edges, b, end, (*seen, start)):
                yield cost + suffix


def test_private_learning_answers_have_independent_arithmetic_oracles() -> None:
    content = StudyContent.model_validate_json(
        (Path(__file__).parents[1] / "fixtures/course_app/content.json").read_bytes()
    )
    weighted = next(unit for unit in content.units if unit.key == "weighted")
    diagram = next(
        block
        for block in weighted.blocks
        if block.kind == "diagram" and any(node.key == "s" for node in block.nodes)
    )
    edges = [(edge.start, edge.end, int(edge.label)) for edge in diagram.edges]
    assert min(paths(edges, "s", "t")) == 5
    assert min(5, 2 + 1) == 3
    assert min(paths([("s", "a", 1), ("s", "b", 2), ("b", "a", -3)], "s", "a")) == -1
    questions = {question.key: question for question in weighted.questions}
    assert len(questions) == 5

    def answer(question):
        return next(o.text for o in question.options if o.key == question.correct)

    assert "cost 5" in answer(questions["cheapest"])
    assert "=3" in answer(questions["update-b"])
    assert answer(questions["negative-case"]) == "−1"
    assert "S→A (2)" in questions["cheapest"].prompt
    assert Fraction(200 * 8 // 10, 200 * 8 // 10 + 800 // 10) == Fraction(2, 3)
