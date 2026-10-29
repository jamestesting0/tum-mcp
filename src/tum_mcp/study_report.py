"""Code-derived review flags for prepared learning content; the agent revises or keeps each."""

import ast
import operator
import re
import statistics
from collections.abc import Iterator

from pydantic import JsonValue

from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.study_content import (
    LITERAL_FIELDS,
    VISUAL_KINDS,
    DiagramBlock,
    StudyContent,
    TableBlock,
    TextBlock,
)
from tum_mcp.study_math import INLINE_SPANS

LONG_PARAGRAPH_WORDS = 110
LONG_PARAGRAPH_SENTENCES = 4
SENTENCE_PARAGRAPH_WORDS = 80
SECTION_WORDS = 90
STATEMENT_WORDS = 80
# About one 390 px phone screen: a question beyond this scrolls before the student can answer.
QUESTION_WORDS = 80
QUESTION_TABLE_ROWS = 6
# Sentences about the material instead of the subject, such as "the lecture groups ...".
META_REFERENCE = re.compile(
    r"\b(?:the|this|our) (?:lecture|course|slides?|lesson|section|page|unit|chapter|textbook) "
    r"(?:groups?|says?|states?|shows?|focus(?:es)?|lists?|defines?|describes?|covers?|calls?|"
    r"presents?|introduces?|explains?|treats?|uses?)\b"
    r"|\bauthored (?:example|network|dataset|domain|chain|trace|graph)\b"
    r"|\b(?:in|as) the (?:table|diagram|figure)(?: above| below)?(?: shows)?,",
    re.IGNORECASE,
)
TITLE_CITATION = re.compile(r"\b(?:slides?|pages?|p\.)\s*\d", re.IGNORECASE)
TRACE_VERBS = re.compile(r"\b(trace|execute|simulate|step through|run|apply)\b", re.IGNORECASE)
# "1 + 0.5 × 6 = 4.5": numbers joined by + - × · * / and an equals sign, outside math and code.
NUMBER = r"\(?[-−]?\d+(?:\.\d+)?\)?"
EQUATION = re.compile(
    rf"(?<![\w.)])(?<![-+×·*/−])(?<![-+×·*/−] )({NUMBER}(?:\s*[-+×·*/−]\s*{NUMBER})+)"
    rf"\s*=\s*([-−]?\d+(?:\.\d+)?)(?!\w|\.\d|\s*[-+×·*/−^]\s*\(?\d)"
)
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _evaluate(node: ast.AST) -> float:
    match node:
        case ast.Expression(body=body):
            return _evaluate(body)
        case ast.Constant(value=int() | float() as value):
            return float(value)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_evaluate(operand)
        case ast.BinOp(left=left, op=op, right=right) if type(op) in OPERATORS:
            return OPERATORS[type(op)](_evaluate(left), _evaluate(right))
        case _:
            raise ValueError("unsupported arithmetic")


def arithmetic_errors(text: str) -> list[str]:
    """Plain arithmetic written in prose whose stated result is wrong."""
    plain = INLINE_SPANS.sub(" ", text)
    errors = []
    for match in EQUATION.finditer(plain):
        expression = re.sub(r"[×·]", "*", match[1]).replace("−", "-")
        try:
            value = _evaluate(ast.parse(expression, mode="eval"))
        except (SyntaxError, ValueError, ZeroDivisionError):
            continue
        if abs(value - float(match[2].replace("−", "-"))) > 1e-6 * max(1.0, abs(value)):
            errors.append(f"{match[0].strip()} (computes to {value:g})")
    return errors


def _strings(value: JsonValue, path: str = "") -> Iterator[tuple[str, str]]:
    match value:
        case str():
            yield path, value
        case list():
            for index, item in enumerate(value):
                yield from _strings(item, f"{path}[{index}]")
        case dict():
            for key, item in value.items():
                if key not in LITERAL_FIELDS:
                    yield from _strings(item, f"{path}.{key}" if path else key)
        case _:
            return


def _sentences(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part])


def quality_flags(
    content: StudyContent | None, exercises: ExerciseContent | None
) -> list[dict[str, JsonValue]]:
    """Measurable signs of hard-to-learn content; each is a prompt to review, not a rule."""
    flags: list[dict[str, JsonValue]] = []

    def flag(item: str, kind: str, detail: str) -> None:
        flags.append({"item": item, "flag": kind, "detail": detail})

    units = content.units if content else ()
    sizes = [len(unit.blocks) for unit in units]
    median = statistics.median(sizes) if sizes else 0
    for unit in units:
        if len(unit.blocks) < median / 2:
            flag(
                unit.key,
                "thin_unit",
                f"{len(unit.blocks)} sections against a course median of {median:g}; check "
                "every outcome of its source is taught.",
            )
        if not any(block.kind in VISUAL_KINDS for block in unit.blocks):
            flag(unit.key, "no_visual", "No diagram, table, formula, code or plot in the lesson.")
        definitions = sum(block.kind == "definition" for block in unit.blocks)
        if definitions > 5:
            flag(unit.key, "many_terms", f"{definitions} definitions in one lesson; split it.")
        for index, block in enumerate(unit.blocks):
            if not isinstance(block, TextBlock):
                continue
            words = sum(len(part.split()) for part in block.paragraphs)
            if words > SECTION_WORDS or len(block.paragraphs) > 2:
                flag(
                    f"{unit.key}#{index}",
                    "long_section",
                    f"'{block.title}': {words} words of prose in {len(block.paragraphs)} "
                    "paragraph(s). Give one idea per section, and a hard idea as short numbered "
                    "steps.",
                )
            for paragraph in block.paragraphs:
                words, sentences = len(paragraph.split()), _sentences(paragraph)
                if words > LONG_PARAGRAPH_WORDS or (
                    sentences > LONG_PARAGRAPH_SENTENCES and words > SENTENCE_PARAGRAPH_WORDS
                ):
                    flag(
                        f"{unit.key}#{index}",
                        "dense_paragraph",
                        f"'{block.title}': {words} words, {sentences} sentences. Split it, or "
                        "show cases as a list or table and steps as a trace.",
                    )
                    break
        traced = any(
            (isinstance(block, DiagramBlock) and len(block.frames) > 1)
            or (block.kind == "code" and block.walkthrough)
            or isinstance(block, TableBlock)
            for block in unit.blocks
        )
        if not traced and any(TRACE_VERBS.search(item.text) for item in unit.objectives):
            flag(
                unit.key,
                "untraced_procedure",
                "An objective asks students to trace or apply a procedure, but the lesson has no "
                "step-by-step diagram, trace table or code walkthrough.",
            )
        narrated = [
            sentence
            for block in unit.blocks
            if isinstance(block, TextBlock)
            for paragraph in (*block.paragraphs, *block.steps, *block.points)
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if META_REFERENCE.search(sentence)
        ]
        if narrated:
            flag(
                unit.key,
                "meta_reference",
                f"{len(narrated)} sentence(s) talk about the material instead of the subject, "
                f"such as '{narrated[0][:90]}'; state the idea itself.",
            )
        cited = [
            block.title
            for block in (*unit.blocks, *(b for q in unit.questions for b in q.blocks))
            if isinstance(getattr(block, "title", None), str) and TITLE_CITATION.search(block.title)
        ]
        if cited:
            flag(
                unit.key,
                "citation_in_title",
                f"{len(cited)} title(s) carry a slide or page number, such as '{cited[0]}'; move "
                "it to the block's pages so the citation opens there.",
            )
        for question in unit.questions:
            words = len(question.prompt.split()) + sum(
                len(option.text.split()) for option in question.options
            )
            rows = max(
                (len(b.rows) for b in question.blocks if isinstance(b, TableBlock)), default=0
            )
            if len(question.blocks) > 1 or words > QUESTION_WORDS or rows > QUESTION_TABLE_ROWS:
                flag(
                    f"{unit.key}/{question.key}",
                    "long_question",
                    f"{len(question.blocks)} context block(s), {rows} table rows and {words} "
                    "words of prompt and options do not fit one phone screen; keep the one "
                    "picture the question needs and trim the rest.",
                )
            prompt = question.prompt.casefold()
            for block in question.blocks:
                if not isinstance(block, TableBlock):
                    continue
                cells = [cell for row in block.rows for cell in row[1:] if len(cell.strip()) > 1]
                if len(block.rows) == 1 or (cells and all(c.casefold() in prompt for c in cells)):
                    flag(
                        f"{unit.key}/{question.key}",
                        "restated_context",
                        f"'{block.title}' repeats what the prompt already says; keep the data in "
                        "one place, or drop the table if the question is simple.",
                    )
            for option in question.options:
                if option.key != question.correct and len(option.feedback.split()) < 5:
                    flag(
                        f"{unit.key}/{question.key}",
                        "thin_feedback",
                        f"Option '{option.key}' feedback does not name the mistake behind it.",
                    )
                    break
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            for block in exercise.statement:
                if not isinstance(block, TextBlock):
                    continue
                words = sum(len(p.split()) for p in (*block.paragraphs, *block.steps))
                parts = len(re.findall(r"\bProblem \d+(?:\.\d+)+", " ".join(block.paragraphs)))
                if words > STATEMENT_WORDS or parts > 1:
                    flag(
                        exercise.key,
                        "dense_statement",
                        f"'{block.title}': {words} words, {parts} parts in one block. Keep the "
                        "wording, but give each part its own block, lists as points, givens as "
                        "a table and the setting as a figure.",
                    )
            for step in exercise.steps:
                item = f"{exercise.key}/{step.key}"
                blank = any(
                    isinstance(block, TableBlock)
                    and any(
                        cell.strip() in {"", "?", "…", "..."} for row in block.rows for cell in row
                    )
                    for block in step.blocks
                )
                if blank and (step.check is None or step.check.kind != "table"):
                    flag(
                        item,
                        "unanswered_table",
                        "The step shows a table to fill in, but Compare does not answer it; make "
                        "it the step's table check or move it to the step that does.",
                    )
                targets = 0
                if step.check and step.check.kind == "table":
                    targets = sum(c.kind != "given" for row in step.check.rows for c in row.cells)
                if step.check and step.check.kind == "graph":
                    targets = len(step.check.answers[0])
                if targets >= 6 and len(step.hints) <= 1:
                    flag(
                        item,
                        "big_step",
                        f"{targets} answers with {len(step.hints)} hint(s); add a hint that "
                        "works the first operation, or split the step.",
                    )
    for name, value in (
        ("study", content.model_dump(mode="json") if content else None),
        ("exercises", exercises.model_dump(mode="json") if exercises else None),
    ):
        for path, text in _strings(value):
            for error in arithmetic_errors(text):
                flag(f"{name}:{path}", "arithmetic", error)
    return flags
