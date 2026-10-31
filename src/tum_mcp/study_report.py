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

# A prose paragraph frames an idea; anything longer becomes steps, points, a table or a figure.
PARAGRAPH_WORDS = 45
PARAGRAPH_SENTENCES = 2
RUN_ON_WORDS = 30
SECTION_WORDS = 70
STATEMENT_WORDS = 80
# About one 390 px phone screen: a question beyond this scrolls before the student can answer.
QUESTION_WORDS = 80
QUESTION_TABLE_ROWS = 6
# Sentences about the material instead of the subject, such as "the lecture groups ...".
META_REFERENCE = re.compile(
    r"\b(?:the|this|our) (?:lecture|course|slides?|lesson|section|page|unit|chapter|textbook) "
    r"(?:groups?|says?|states?|shows?|focus(?:es)?|lists?|defines?|describes?|covers?|calls?|"
    r"presents?|introduces?|explains?|treats?|uses?|gives?|tests?|checks?|notes?|mentions?|"
    r"discuss(?:es)?|assumes?|emphasi[sz]es?)\b"
    r"|\bauthored (?:example|network|dataset|domain|chain|trace|graph)\b"
    r"|\b(?:in|as) the (?:table|diagram|figure)(?: above| below)?(?: shows)?,",
    re.IGNORECASE,
)
# Mathematics typed as plain text: Greek letters, math symbols, sub/superscripts, a function
# applied to a condition or several arguments (P(A|B), Q(S, a)) or a one-letter equation (V = 3).
PLAIN_MATH = re.compile(
    r"[\u0391-\u03a9\u03b1-\u03c9≤≥≠≈∑∏∫√∞∀∃¬∧∨⇒⇔→∈∉⊂⊆∪∩×÷²³⁰-⁹₀-₉ᵈⁿ]"
    r"|(?:\d|\b[A-Za-z]\b|\))\s*−\s*[\w(]"
    r"|\b[A-Z][A-Za-z]{0,2}\([^()\n]*[|=,][^()\n]*\)"
    r"|(?<![\w.])[A-Za-z]\*?(?:\([^()\n]{1,12}\))?\s*[=<>]\s*[-\w(]"
)
# Text that spells out an object the student should see: "the diagonal matrix with entries 1, 0",
# "a vector whose components are ...", "the graph has edges ...".
# Only a listing of the object's own values counts; "a graph with n vertices" states a size.
DESCRIBED_OBJECT = re.compile(
    r"\b(?:matrix|matrices|vectors?|tuple|table|graph|tree|grid|array)\b[^.;:]{0,30}?"
    r"\b(?:with|whose|has|have|having|contains?)\b[^.;:]{0,25}?"
    r"\b(?:entries|entry|components?|elements?|rows?|columns?|edges?|cells?|values)\b"
    r"\s*(?:are|is|of|equal to|=|:)?\s*(?:\\\(|[-\u2212]?\d|[A-Z]\s*[-\u2013\u2192]\s*[A-Z]\b)",
    re.IGNORECASE,
)
# Inline vectors and matrices read well up to a 2x2 or a short column; larger ones need a
# display formula, as Notion's "turn into block equation".
INLINE_MATRIX = re.compile(
    r"\\begin\{([pbvBV]?matrix|smallmatrix|array)\}(.*?)\\end\{\1\}", re.DOTALL
)
# An identity over this many distinct symbols inside a sentence asks the reader to decode
# notation and follow the claim at once: (<a| (x) <b|)(|c> (x) |d>) = <a|c><b|d>.
IDENTITY_SYMBOLS = 4
INLINE_MATRIX_ROWS = 3
INLINE_MATRIX_COLUMNS = 2
# Greek letters name quantities a newcomer must be told about before relying on them.
GREEK = re.compile(
    r"\\(?:var)?(alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|pi|"
    r"rho|sigma|tau|upsilon|phi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|"
    r"Omega)(?![A-Za-z])"
)
# A unit's opening may introduce a few new symbols and terms; more before any concrete case,
# picture or example leaves a first-time reader holding names they cannot yet picture.
OPENING_NEW_IDEAS = 3
CONCRETE_KINDS = frozenset({"figure", "diagram", "plot", "table", "derivation", "code", "uml"})
NON_PROSE = frozenset({"key", "sources", "pages", "kind", "image", "language", "course_key"})
DRAWN = frozenset({"diagram", "plot", "figure", "code"})
TITLE_CITATION = re.compile(r"\b(?:slides?|pages?|p\.)\s*\d", re.IGNORECASE)
ASIDE_TITLE = re.compile(r"\b(?:assumptions?|sources?|references?)\b", re.IGNORECASE)
FLAT_OUTLINE_UNITS = 4
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


def _plain_latex(expression: str) -> str:
    for command, symbol in ((r"\times", "×"), (r"\cdot", "·"), (r"\,", " "), ("{", ""), ("}", "")):
        expression = expression.replace(command, symbol)
    return expression


def arithmetic_errors(text: str) -> list[str]:
    """Plain arithmetic written in prose whose stated result is wrong."""
    # Inline code stays unread; numeric LaTeX is read with its operators as plain symbols.
    plain = INLINE_SPANS.sub(
        lambda span: " " if span[1] is None else f" {_plain_latex(span[1])} ", text
    )
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


def _name(block) -> str:
    return block.title or block.kind


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
    if len(units) >= FLAT_OUTLINE_UNITS and not any(unit.path for unit in units):
        flag(
            "outline",
            "flat_outline",
            f"{len(units)} units in one flat list; give each a `path` such as its lecture, "
            "week or topic so the outline folds them into groups.",
        )
    seen_symbols: set[str] = set()
    seen_terms: set[str] = set()
    for unit in units:
        opening, symbols, terms = _opening(unit.blocks, seen_symbols, seen_terms)
        if len(opening) >= OPENING_NEW_IDEAS:
            flag(
                unit.key,
                "dense_introduction",
                f"The opening introduces {', '.join(opening[:6])} before any picture, example "
                "or worked case. Say first what the idea describes and why it matters, tie it to "
                "what the reader already knows, then name its parts one at a time.",
            )
        seen_symbols |= symbols
        seen_terms |= terms
        worked = any(
            block.kind == "derivation"
            or (
                isinstance(block, TextBlock)
                and any(
                    "=" in step and re.search(r"\d", step) for step in (*block.steps, *block.points)
                )
            )
            for block in unit.blocks
        )
        if worked and not any(block.kind == "formula" for block in unit.blocks):
            flag(
                unit.key,
                "example_without_rule",
                "The lesson works numbers through but states no general rule. Give the reusable "
                "formula as a formula block with its symbols and conditions, link it to the "
                "worked case, and apply it once more to different numbers.",
            )
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
        reading_blocks = (*unit.blocks, *(block for item in unit.explore for block in item.blocks))
        passages = [
            *((f"{unit.key}#{index}", block) for index, block in enumerate(unit.blocks)),
            *(
                (f"{unit.key}/explore/{item.key}#{index}", block)
                for item in unit.explore
                for index, block in enumerate(item.blocks)
            ),
        ]
        for location, block in passages:
            if not isinstance(block, TextBlock):
                continue
            words = sum(len(part.split()) for part in block.paragraphs)
            if words > SECTION_WORDS or len(block.paragraphs) > 2:
                flag(
                    location,
                    "long_section",
                    f"'{_name(block)}': {words} words of prose in {len(block.paragraphs)} "
                    "paragraph(s). Give one idea per section, and a hard idea as short numbered "
                    "steps.",
                )
            calculation = next((part for part in block.paragraphs if part.count("=") >= 2), None)
            if calculation is not None:
                flag(
                    location,
                    "prose_calculation",
                    f"'{_name(block)}': a chain of calculations inside a sentence. Give each "
                    "computed value as its own step: what is computed, the expression, the result.",
                )
            dense = [
                (len(part.split()), _sentences(part))
                for part in block.paragraphs
                if len(part.split()) > PARAGRAPH_WORDS
                or (_sentences(part) > PARAGRAPH_SENTENCES and len(part.split()) > RUN_ON_WORDS)
            ]
            if dense:
                words, sentences = dense[0]
                flag(
                    location,
                    "dense_paragraph",
                    f"'{_name(block)}': {words} words, {sentences} sentences. Keep one or two "
                    "framing sentences; give a procedure as labelled steps, conditions as points "
                    "and cases as a table.",
                )
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
            for block in reading_blocks
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
            for block in (*reading_blocks, *(b for q in unit.questions for b in q.blocks))
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
                        f"'{_name(block)}' repeats what the prompt already says; keep the data in "
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
            if len(exercise.parts) > 1 and not any(step.part for step in exercise.steps):
                flag(
                    exercise.key,
                    "shared_guide",
                    f"{len(exercise.parts)} parts share one guide; name each step's `part` so "
                    "every part gets its own guide.",
                )
            # A released statement may cite its lecture; authored guidance and solutions may not.
            authored = [
                text
                for step in exercise.steps
                for text in (
                    step.prompt,
                    *step.hints,
                    step.explanation,
                    *(
                        part
                        for block in (
                            *step.blocks,
                            *(
                                step.check.model_answer
                                if step.check
                                and step.check.kind == "self_check"
                                and isinstance(step.check.model_answer, tuple)
                                else ()
                            ),
                        )
                        if isinstance(block, TextBlock)
                        for part in (*block.paragraphs, *block.steps, *block.points)
                    ),
                )
            ] + [
                part
                for block in exercise.solution.blocks
                if isinstance(block, TextBlock)
                for part in (*block.paragraphs, *block.steps, *block.points)
            ]
            narrated = [
                sentence
                for text in authored
                for sentence in re.split(r"(?<=[.!?])\s+", text)
                if META_REFERENCE.search(sentence)
            ]
            if narrated:
                flag(
                    exercise.key,
                    "meta_reference",
                    f"{len(narrated)} sentence(s) in the guide or solution talk about the material "
                    f"instead of the subject, such as '{narrated[0][:90]}'; state the idea itself.",
                )
            asides = [
                block.title
                for block in (*exercise.statement, *exercise.solution.notes)
                if block.title and ASIDE_TITLE.search(block.title)
            ]
            if asides:
                flag(
                    exercise.key,
                    "assumption_aside",
                    f"'{asides[0]}' sets assumptions or sources apart; state assumptions in the "
                    "problem statement and leave sources to the citation button.",
                )
            for block in exercise.statement:
                if not isinstance(block, TextBlock):
                    continue
                words = sum(len(p.split()) for p in (*block.paragraphs, *block.steps))
                parts = len(re.findall(r"\bProblem \d+(?:\.\d+)+", " ".join(block.paragraphs)))
                if words > STATEMENT_WORDS or parts > 1:
                    flag(
                        exercise.key,
                        "dense_statement",
                        f"'{_name(block)}': {words} words, {parts} parts in one block. Keep the "
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
                # Compare answers that list several computed results in one running sentence
                # leave the student nothing to compare their working against.
                answer = (
                    step.check.model_answer
                    if step.check
                    and step.check.kind == "self_check"
                    and isinstance(step.check.model_answer, tuple)
                    else ()
                )
                if any(
                    isinstance(block, TextBlock)
                    and any(part.count("=") >= 3 for part in (*block.paragraphs, *block.points))
                    for block in (*step.blocks, *answer)
                ):
                    flag(
                        item,
                        "compressed_working",
                        "Several results are computed inside one sentence; show the working as "
                        "a derivation block, one transformation per line with its reason, and "
                        "one labelled group per requested result.",
                    )
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
        plain: dict[str, list[str]] = {}
        identities: dict[str, list[str]] = {}
        described: dict[str, list[str]] = {}
        tall: dict[str, list[str]] = {}
        for item, text in _prose(value):
            prose = INLINE_SPANS.sub(" ", text)
            found = PLAIN_MATH.search(prose)
            if found:
                plain.setdefault(item, []).append(found[0])
            if spelled := DESCRIBED_OBJECT.search(text):
                described.setdefault(item, []).append(spelled[0])
            for expression in INLINE_SPANS.finditer(text):
                latex = expression[1] or ""
                letters = set(re.findall(r"(?<![\\A-Za-z])[A-Za-z](?![A-Za-z])", latex))
                if "=" in latex and len(letters) >= IDENTITY_SYMBOLS:
                    identities.setdefault(item, []).append(latex[:60])
                for matrix in INLINE_MATRIX.finditer(latex):
                    rows = [row for row in re.split(r"\\\\", matrix[2]) if row.strip()]
                    columns = max(row.count("&") + 1 for row in rows) if rows else 0
                    if len(rows) > INLINE_MATRIX_ROWS or columns > INLINE_MATRIX_COLUMNS:
                        tall.setdefault(item, []).append(f"{len(rows)}x{columns}")
        for item, samples in identities.items():
            flag(
                item,
                "unexplained_identity",
                f"{len(samples)} general identity(ies) with several symbols inside a sentence, "
                f"such as '\\({samples[0]}\\)'. Say what each symbol stands for where it is "
                "used, show the worked case first, then give the identity as a formula block "
                "with its symbols and conditions.",
            )
        for item, samples in described.items():
            flag(
                item,
                "described_object",
                f"{len(samples)} text(s) spell out an object instead of showing it, such as "
                f"'{samples[0]}'. Show the matrix, vector, table or graph itself and let the "
                "text say what to notice in it.",
            )
        for item, samples in tall.items():
            flag(
                item,
                "tall_inline_math",
                f"{len(samples)} inline matrix or vector(s) of size {samples[0]} inside a "
                "sentence; set anything larger than a 2x2 matrix or a three-entry column as a "
                "formula block.",
            )
        for item, samples in plain.items():
            flag(
                item,
                "plain_math",
                f"{len(samples)} text(s) type mathematics as plain characters, such as "
                f"'{samples[0]}'. Write every symbol, variable and formula as inline LaTeX: "
                r"\(P(A \mid B)\), \(\gamma\), \(V = 3\).",
            )
    return flags


def _texts(block) -> Iterator[str]:
    match block:
        case TextBlock():
            yield from (*block.paragraphs, *block.steps, *block.points)
        case _ if block.kind == "definition":
            yield block.statement
        case _:
            return


def _opening(
    blocks: tuple, seen_symbols: set[str], seen_terms: set[str]
) -> tuple[list[str], set[str], set[str]]:
    """New symbols and terms met before the unit's first concrete block, and all it introduces."""
    opening: list[str] = []
    symbols: set[str] = set()
    terms: set[str] = set()
    concrete = False
    for block in blocks:
        concrete = concrete or block.kind in CONCRETE_KINDS
        found: list[str] = []
        if block.kind == "definition":
            found.append(f"'{block.term}'")
            terms.add(block.term.casefold())
        if block.kind == "formula":
            for symbol in block.symbols:
                symbols.update(GREEK.findall(symbol.symbol))
        for text in _texts(block):
            for expression in INLINE_SPANS.finditer(text):
                for name in GREEK.findall(expression[1] or ""):
                    if name not in seen_symbols and name not in symbols:
                        found.append(rf"\(\{name}\)")
                    symbols.add(name)
        if not concrete:
            opening += [item for item in found if item not in opening]
    return opening, symbols, terms - seen_terms


def _prose(value: JsonValue, item: str = "") -> Iterator[tuple[str, str]]:
    """Rendered text with the unit or exercise it belongs to; drawings and code are skipped."""
    match value:
        case str():
            yield item, value
        case list():
            for entry in value:
                yield from _prose(entry, item)
        case dict() if value.get("kind") not in DRAWN:
            owner = value.get("key") if "blocks" in value or "statement" in value else None
            for field, entry in value.items():
                if field not in LITERAL_FIELDS and field not in NON_PROSE:
                    yield from _prose(entry, owner if isinstance(owner, str) else item)
        case _:
            return
