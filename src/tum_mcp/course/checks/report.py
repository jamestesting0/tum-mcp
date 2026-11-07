"""Code-derived review flags for prepared learning content; the agent revises or keeps each."""

import ast
import operator
import re
import statistics
from collections.abc import Iterator
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.latex import (
    INLINE_SPANS,
    decorated_variants,
    formula_parts,
    normalize_symbol,
    split_relation,
    symbol_latex,
    symbol_occurs,
)
from tum_mcp.course.content.study import (
    LITERAL_FIELDS,
    MARKS,
    CodeBlock,
    DerivationBlock,
    DiagramBlock,
    StudyContent,
    TableBlock,
    TextBlock,
    WalkthroughBlock,
    declared_meanings,
    has_visual,
)
from tum_mcp.course.project.models import StudyState

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
# An action hidden in a noun: "perform the computation of", "carry out an evaluation of".
NOMINALISATION = re.compile(
    r"\b(?:perform|performs|performing|carry out|carries out|conduct|conducts|undertake|"
    r"make|makes|achieve|achieves)\s+(?:a|an|the)?\s*\w+(?:tion|ment|sion|ance|ence)\s+of\b",
    re.IGNORECASE,
)
# A sheet's framing of an exercise, which states no given or task: "This exercise should
# refresh your knowledge…", "In this sheet you will…".
STATEMENT_FRAMING = re.compile(
    r"\b(?:this|the following|today's) (?:exercise|sheet|task|problem|worksheet)s? "
    r"(?:should|will|is meant to|aims? to|helps?|lets? you|is designed to)\b"
    r"|\brefresh your (?:knowledge|memory|skills)\b"
    r"|\bin this (?:exercise|sheet|task),? (?:we|you) (?:will|are going to|practi[sc]e)\b",
    re.IGNORECASE,
)
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
# Mathematics read aloud in words ("theta over two", "lambda squared", "one over n"); names such
# as "beta distribution" stay, because no operation follows them.
SPOKEN_GREEK = (
    r"(?:alpha|beta|gamma|delta|epsilon|zeta|eta|theta|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau"
    r"|phi|varphi|chi|psi|omega)"
)
SPOKEN_TERM = rf"(?:{SPOKEN_GREEK}|one|two|three|four|five|six|eight|ten|[a-z])"
SPOKEN_MATH = re.compile(
    rf"\b{SPOKEN_GREEK}\s+(?:over|squared|cubed|times|plus|minus|divided by|to the power of)\b"
    rf"|\b{SPOKEN_TERM}\s+over\s+{SPOKEN_TERM}\b"
    rf"|\bsquare root of\s+{SPOKEN_TERM}\b",
    re.IGNORECASE,
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
CONCRETE_KINDS = frozenset(
    {"figure", "diagram", "plot", "table", "derivation", "code", "uml", "walkthrough"}
)
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


_GREEK_NAMES = (
    "alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|rho|sigma|tau"
    "|upsilon|phi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|Omega"
)
# A variable a reader may not recall: a Greek letter (not pi) or a subscripted letter.
CANDIDATE_VARIABLE = re.compile(
    rf"\\(?:var)?(?:{_GREEK_NAMES})(?![A-Za-z])(?:_\{{[^{{}}]*\}}|_[A-Za-z0-9])?"
    rf"|(?<![\\A-Za-z])[A-Za-z]_(?:\{{[^{{}}]*\}}|[A-Za-z0-9])"
)
_FILLER_WORDS = {"the", "a", "an", "symbol", "variable", "sub", "of", "is"}
# In a task (an exercise, a pattern's examples and drill) a lone letter such as k is a quantity
# the student is given or asked for; the imaginary unit, e, the identity and big-O are notation.
_NOTATION_GROUP = re.compile(
    r"\\(?:text[a-z]*|mathrm|operatorname|mbox|begin|end)\s*\{[^{}]*\}"
    r"|\\math(?:bb|cal|frak|scr|bf|sf)\s*(?:\{[^{}]*\}|[A-Za-z])"
)
_SCRIPT_GROUP = re.compile(r"([_^])\{[^{}]*\}")
_LONE_LETTER = re.compile(r"(?<![\\A-Za-z_^])[A-Za-z](?![A-Za-z_])")
_NOTATION_LETTERS = {"i", "e", "I", "O"}
# A meaning made only of these words says nothing about the variable ("Given quantities").
_GENERIC_WORDS = {
    "given", "known", "unknown", "supplied", "provided", "quantity", "quantities", "value",
    "values", "number", "numbers", "parameter", "parameters", "input", "inputs", "result",
    "constant", "constants", "term", "terms", "variables", "symbols", "and",
}  # fmt: skip


def unexplained_variables(context: JsonValue, task: bool = False) -> list[str]:
    """Greek, subscripted or decorated variables in a context's derivations and applied formulas
    that no meaning list and no inline mention in its text explains; in a task, lone letters
    too."""
    formulas: list[str] = []
    spans: list[str] = []
    known = {normalize_symbol(item["symbol"]) for item in declared_meanings(context)}

    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            if value.get("kind") == "derivation":
                formulas.extend(
                    line["latex"] for group in value["groups"] for line in group["lines"]
                )
            elif isinstance(value.get("math"), list):
                formulas.extend(line for line in value["math"] if isinstance(line, str))
            if "latex" in value and isinstance(value.get("symbols"), list):
                known.update(normalize_symbol(item["symbol"]) for item in value["symbols"])
            # A meaning list's own symbol is no mention in the text.
            for key, item in value.items():
                if key != "symbol":
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            spans.extend(match[1] for match in INLINE_SPANS.finditer(value) if match[1])

    visit(context)
    found: list[str] = []
    for latex in formulas:
        tokens = [match[0] for match in CANDIDATE_VARIABLE.finditer(latex)]
        tokens += decorated_variants(latex, sorted(known))
        if task:
            plain = _SCRIPT_GROUP.sub(r"\1", _NOTATION_GROUP.sub(" ", latex))
            tokens += [m[0] for m in _LONE_LETTER.finditer(plain) if m[0] not in _NOTATION_LETTERS]
        for token in map(normalize_symbol, tokens):
            if token in known or token in found or any(symbol_occurs(s, token) for s in spans):
                continue
            found.append(token)
    return found


# A figure label that types mathematics instead of writing it as LaTeX: Greek, scripts, kets
# or a letter run into its index ("x3"). The app typesets \\(x_3\\) like the text around it.
_LABEL_TEXT = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S)
_TYPED_MATH = re.compile(
    r"[\u0391-\u03a9\u03b1-\u03c9\u2080-\u2089\u2070-\u2079\u00b2\u00b3\u27e8\u27e9\u2032]"
    r"|^[A-Za-z](?:_?[0-9]{1,2}|_[A-Za-z])$"
)


def typed_math_labels(context: JsonValue) -> list[str]:
    """Figure labels that type mathematics as characters instead of inline LaTeX."""
    found: list[str] = []

    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            if value.get("kind") == "figure" and isinstance(value.get("svg"), str):
                for raw in _LABEL_TEXT.findall(value["svg"]):
                    label = re.sub(r"<[^>]+>", "", raw).strip()
                    if "\\(" not in label and _TYPED_MATH.search(label):
                        found.append(label)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(context)
    return found


def generic_meanings(context: JsonValue) -> list[str]:
    """Meanings that say only that a variable is given or is a value ("Given quantities")."""
    found: list[str] = []

    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            symbols = value.get("symbols")
            for item in symbols if isinstance(symbols, list) else ():
                words = re.sub(r"[^a-z ]", " ", str(item.get("meaning", "")).lower()).split()
                if words and all(w in _GENERIC_WORDS or w in _FILLER_WORDS for w in words):
                    found.append(str(item.get("symbol")))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(context)
    return found


def renamed_meanings(context: JsonValue) -> list[str]:
    """Meanings that only spell the variable's name ("rho", "p sub i")."""
    found: list[str] = []

    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            symbols = value.get("symbols")
            for item in symbols if isinstance(symbols, list) else ():
                words = re.sub(r"[^a-z ]", " ", str(item.get("meaning", "")).lower()).split()
                said = "".join(word for word in words if word not in _FILLER_WORDS)
                latex = symbol_latex(str(item.get("symbol", ""))).lower().replace("\\var", "")
                name = re.sub(r"[^a-z]", "", latex)
                if said and said == name:
                    found.append(str(item["symbol"]))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(context)
    return found


def echoed_meanings(context: JsonValue) -> list[str]:
    """Meanings that the text beside their formula (an applied formula's text, a line's
    reason) already says."""
    found: list[str] = []

    def words(text: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9 ]", " ", INLINE_SPANS.sub(" ", text).lower()).split())

    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            symbols = value.get("symbols")
            if isinstance(symbols, list) and (value.get("kind") == "derivation" or "math" in value):
                beside = [str(value.get("text") or "")] + [
                    str(line.get("reason") or "")
                    for group in value.get("groups", [])
                    for line in group.get("lines", [])
                ]
                said = words(" ".join(beside))
                for item in symbols:
                    meaning = words(str(item.get("meaning", "")))
                    if len(meaning.split()) >= 3 and meaning in said:
                        found.append(str(item["symbol"]))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(context)
    return found


def redeclared_meanings(context: JsonValue) -> list[str]:
    """Variables given the same meaning on several formulas of one context; one serves all."""
    seen: dict[tuple[str, str], int] = {}
    for item in declared_meanings(context):
        key = (normalize_symbol(item["symbol"]), " ".join(item["meaning"].lower().split()))
        seen[key] = seen.get(key, 0) + 1
    return [symbol for (symbol, _), count in seen.items() if count > 1]


def variable_flags(item: str, context: JsonValue, task: bool = False) -> list[dict[str, JsonValue]]:
    flags: list[dict[str, JsonValue]] = []
    if typed := typed_math_labels(context):
        flags.append(
            {
                "item": item,
                "flag": "typed_math_label",
                "detail": f"{len(typed)} figure label(s) type mathematics as characters, such as "
                f"'{typed[0]}'. Write the whole label as inline LaTeX (\\(x_3\\), "
                "\\(|1\\rangle\\)) so the app typesets it like the text.",
            }
        )
    if generic := generic_meanings(context):
        flags.append(
            {
                "item": item,
                "flag": "generic_meaning",
                "detail": f"{len(generic)} meaning(s) say only that a variable is given or is a "
                f"value, such as {generic[0]}. Say what each quantity is in this task, one "
                "variable per entry.",
            }
        )
    if repeated := redeclared_meanings(context):
        flags.append(
            {
                "item": item,
                "flag": "redeclared_meaning",
                "detail": f"{len(repeated)} variable(s) carry the same meaning on several "
                f"formulas, such as {repeated[0]}. Keep it on the first; the app reuses it in "
                "this context.",
            }
        )
    if missing := unexplained_variables(context, task):
        flags.append(
            {
                "item": item,
                "flag": "unexplained_symbol",
                "detail": f"{len(missing)} variable(s) in displayed working have no meaning "
                f"here, such as {', '.join(missing[:3])}. Give a meaning where a reviser would "
                "stop to recall it (see the variables guide); leave obvious ones.",
            }
        )
    if echoed := echoed_meanings(context):
        flags.append(
            {
                "item": item,
                "flag": "echoed_meaning",
                "detail": f"{len(echoed)} meaning(s) are also said in the text beside the formula, "
                f"such as {echoed[0]}. Keep the meaning on the formula and cut it from the text.",
            }
        )
    if renamed := renamed_meanings(context):
        flags.append(
            {
                "item": item,
                "flag": "renamed_meaning",
                "detail": f"{len(renamed)} meaning(s) only spell the variable's name, such as "
                f"{renamed[0]}. Say what it is here.",
            }
        )
    return flags


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


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


def stepped(block: object) -> bool:
    """A block that walks through a process one step at a time."""
    return (
        isinstance(block, WalkthroughBlock)
        or (isinstance(block, DiagramBlock) and len(block.frames) > 1)
        or (isinstance(block, CodeBlock) and bool(block.walkthrough))
        or (isinstance(block, DerivationBlock) and block.walkthrough)
    )


def _sections(blocks: tuple) -> list[tuple[str, list]]:
    """Blocks grouped as the app shows them: a titled block and the untitled ones after it."""
    sections: list[tuple[str, list]] = []
    for block in blocks:
        if block.kind != "definition" and block.title or not sections:
            sections.append((block.key or _name(block), [block]))
        else:
            sections[-1][1].append(block)
    return sections


# A computed result stated in inline math: a calculation equal to a plain number
# ("\(2^3 = 8\)", "\(f(G) = 18\)") or a complexity bound ("\(O(b^d)\)"). A given such as
# "\(b = 2\)" has a bare symbol on the left and is not a result.
UNWORKED_RESULT = re.compile(
    r"\\\((\s*[^()=]*?(?:[-+*^/(]|\\cdot|\\times|\\frac|\\sum)[^=]*?=\s*-?\d+(?:\.\d+)?\s*"
    r"|\s*[^=]*?=\s*O\([^)]*\)\s*)\\\)"
)
# Bookkeeping a student should never read: where a file came from or who wrote it.
PROVENANCE = re.compile(
    r"\b(?:user[- ]provided|agent[- ](?:written|authored)|uploaded by|imported from|"
    r"sample solution|official solution|provenance)\b",
    re.IGNORECASE,
)


# Four or more members run together in one sentence: "a, b, c and d".
INLINE_LIST = re.compile(
    r"(?:\b[\w-]+(?: [\w-]+){0,3}, ){2,}[\w-]+(?: [\w-]+){0,3},? (?:and|or) [\w-]+"
)


# Three or more labelled lines run together in one paragraph: "Premise 1: … Premise 2: …".
INLINE_STEPS = re.compile(r"(?:^|[.;]\s+)(?:[A-Z][a-z]+(?: \d+)?): ")


def visual_state_flags(item: str, value: JsonValue) -> list[dict[str, JsonValue]]:
    """A staged walkthrough needs changing marks, not only changing prose."""
    flags: list[dict[str, JsonValue]] = []

    def visit(value: JsonValue) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            if value.get("kind") == "walkthrough" and isinstance(stage := value.get("stage"), dict):
                marks = MARKS[str(stage["kind"])]
                variant = value.get("variant")
                runs = [value, *([variant] if isinstance(variant, dict) else [])]
                for run in runs:
                    states = [{key: step.get(key) for key in marks} for step in run["steps"]]
                    if all(state == states[0] for state in states[1:]):
                        flags.append(
                            {
                                "item": item,
                                "flag": "static_walkthrough",
                                "detail": f"Walkthrough '{value.get('title') or value.get('key')}' "
                                f"changes its text but not its {stage['kind']} stage. "
                                f"Show the actual step state with {', '.join(sorted(marks))}, "
                                "or present an intentionally static figure outside a walkthrough.",
                            }
                        )
            for child in value.values():
                visit(child)

    visit(value)
    return flags


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
        flags.extend(variable_flags(unit.key, unit.model_dump(mode="json")))
        flags.extend(visual_state_flags(unit.key, unit.model_dump(mode="json")))
        opening, symbols, terms = _opening(unit.blocks, seen_symbols, seen_terms)
        if len(opening) >= OPENING_NEW_IDEAS:
            flag(
                unit.key,
                "dense_introduction",
                f"The opening introduces {', '.join(opening[:6])} before any picture, example "
                "or worked case. Check whether a first-time reader learns what the idea describes, "
                "why it matters and how it ties to what they know before its parts are named.",
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
                "The lesson works numbers through but has no formula block. Check whether the "
                "topic has a reusable rule; if so, state it with its symbols and conditions and "
                "apply it once more to different numbers.",
            )
        derived = [
            line.latex
            for block in unit.blocks
            if block.kind == "derivation"
            for group in block.groups
            for line in group.lines
        ]
        # A line listing several statements ("N=4,\quad M=1") is no transformation the app can
        # align; a line without a top-level relation has nothing to align on.
        listed = [latex for latex in derived if len(formula_parts(latex)) > 1]
        unaligned = [
            latex for latex in derived if latex not in listed and not split_relation(latex)[1]
        ]
        if unaligned:
            flag(
                unit.key,
                "unaligned_line",
                f"{len(unaligned)} derivation line(s) have no relation to align on, such as "
                f"'{unaligned[0][:60]}'. Write the relation (\\(x = \\dots\\)) or join the line to "
                "the one it continues.",
            )
        if listed:
            flag(
                unit.key,
                "listed_derivation_line",
                f"{len(listed)} derivation line(s) list several statements, such as "
                f"'{listed[0][:60]}'. Give each line one transformation; put givens one per "
                "line or in the text before the derivation.",
            )
        if len(unit.blocks) < median / 2:
            flag(
                unit.key,
                "thin_unit",
                f"{len(unit.blocks)} sections against a course median of {median:g}; check "
                "every outcome of its source is taught.",
            )
        summary = _normalized(unit.summary)
        if any(_normalized(objective.text) == summary for objective in unit.objectives):
            flag(
                unit.key,
                "summary_repeats_objective",
                "The summary repeats an objective word for word; let it state the question the "
                "unit answers.",
            )
        if not has_visual(unit.blocks):
            flag(unit.key, "no_visual", "No diagram, table, formula, code or plot in the lesson.")
        for question in unit.questions:
            if not has_visual(question.blocks):
                flag(
                    f"{unit.key}/{question.key}",
                    "text_only_question",
                    "The question has no code, diagram, table, formula or plot carrying its "
                    "context. Reframe it around a useful case, not a decorative picture.",
                )
        definitions = sum(block.kind == "definition" for block in unit.blocks)
        if definitions > 5:
            flag(
                unit.key,
                "many_terms",
                f"{definitions} definitions in one lesson; check whether it holds more than one "
                "topic.",
            )
        for index, block in enumerate(unit.blocks):
            listed = [
                found.group(0)
                for paragraph in getattr(block, "paragraphs", ())
                if isinstance(block, TextBlock) and (found := INLINE_LIST.search(paragraph))
            ]
            if any(
                len(INLINE_STEPS.findall(paragraph)) >= 3
                for paragraph in getattr(block, "paragraphs", ())
                if isinstance(block, TextBlock)
            ):
                flag(
                    f"{unit.key}#{index}",
                    "inline_steps",
                    "Labelled lines run together in one paragraph; give each its own line, as a "
                    "list, a derivation or a formula.",
                )
            if listed:
                flag(
                    f"{unit.key}#{index}",
                    "inline_list",
                    f"Members run together in a sentence: '{listed[0][:90]}'; give them as a list "
                    "or table the student can scan.",
                )
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
                    "paragraph(s). Check whether it holds more than one idea; a hard idea reads "
                    "better as short numbered steps.",
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
        # A procedure is traced when it is stepped through, each step with what it does.
        traced = any(stepped(block) for block in unit.blocks)
        if not traced and any(TRACE_VERBS.search(item.text) for item in unit.objectives):
            if any(isinstance(block, TableBlock) for block in unit.blocks):
                flag(
                    unit.key,
                    "static_trace",
                    "An objective asks students to trace a procedure, but the lesson shows it only "
                    "as a finished table. Step through it with a walkthrough so each step says "
                    "what is done and why.",
                )
            else:
                flag(
                    unit.key,
                    "untraced_procedure",
                    "An objective asks students to trace or apply a procedure, but the lesson has "
                    "no walkthrough, stepped diagram or code walkthrough.",
                )
        for section, members in _sections(unit.blocks):
            if any(stepped(block) or block.kind in {"code", "derivation"} for block in members):
                continue
            results = [
                found
                for block in members
                if isinstance(block, TextBlock)
                for text in (*block.paragraphs, *block.steps, *block.points)
                for found in UNWORKED_RESULT.findall(text)
            ]
            if results:
                flag(
                    f"{unit.key}/{section}",
                    "unworked_result",
                    f"'\\({results[0]}\\)' states a computed result with no working in its "
                    "section. Show how it is reached: a derivation or a walkthrough.",
                )
        for block in unit.blocks:
            frame = block.frames[0] if isinstance(block, DiagramBlock) else None
            if (
                frame
                and len(block.frames) == 1
                and (frame.visited or frame.frontier or frame.state)
            ):
                flag(
                    f"{unit.key}/{block.key or _name(block)}",
                    "single_frame_diagram",
                    f"'{_name(block)}' shows one moment of a process. If students must follow "
                    "how it gets there, step through it as a walkthrough.",
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
        nominal = [
            sentence
            for block in reading_blocks
            if isinstance(block, TextBlock)
            for paragraph in (*block.paragraphs, *block.steps, *block.points)
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if NOMINALISATION.search(sentence)
        ]
        if nominal:
            flag(
                unit.key,
                "nominalisation",
                f"{len(nominal)} sentence(s) hide the action in a noun, such as "
                f"'{nominal[0][:90]}'; use the verb ('compute', not 'perform the computation of').",
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
                cells = [
                    cell.strip().casefold() for row in block.rows for cell in row if cell.strip()
                ]
                if cells and all(
                    re.search(r"(?<!\w)" + re.escape(cell) + r"(?!\w)", prompt) for cell in cells
                ):
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
        # A set summary is teaching text: what the sheet practises, not where it came from.
        if (
            group.summary
            and group.exercises
            and (META_REFERENCE.search(group.summary) or PROVENANCE.search(group.summary))
        ):
            flag(
                group.exercises[0].key,
                "meta_reference",
                f"The summary of '{group.title}' talks about the material or its origin; say what "
                "the sheet practises and keep provenance in the ledger.",
            )
        for exercise in group.exercises:
            flags.extend(variable_flags(exercise.key, exercise.model_dump(mode="json"), task=True))
            flags.extend(visual_state_flags(exercise.key, exercise.model_dump(mode="json")))
            guided = (*exercise.statement, *(b for step in exercise.steps for b in step.blocks))
            if not has_visual(guided):
                flag(
                    exercise.key,
                    "text_only_question",
                    "Neither the statement nor a guide step shows a code snippet, diagram, "
                    "formula, table or plot; add one to a guide step where it carries information.",
                )
            if len(exercise.parts) > 1 and not any(step.part for step in exercise.steps):
                flag(
                    exercise.key,
                    "shared_guide",
                    f"{len(exercise.parts)} parts share one guide; name each step's `part` so "
                    "every part gets its own guide.",
                )
            authored = (
                [
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
                ]
                + [
                    part
                    for block in exercise.solution.blocks
                    if isinstance(block, TextBlock)
                    for part in (*block.paragraphs, *block.steps, *block.points)
                ]
                + [
                    part
                    for block in exercise.statement
                    if isinstance(block, TextBlock)
                    for part in (*block.paragraphs, *block.steps, *block.points)
                ]
            )
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
                    f"{len(narrated)} sentence(s) in the statement, guide or solution talk "
                    "about the material "
                    f"instead of the subject, such as '{narrated[0][:90]}'; state the idea itself.",
                )
            framing = [
                sentence
                for block in exercise.statement
                if isinstance(block, TextBlock)
                for part in (*block.paragraphs, *block.steps, *block.points)
                for sentence in re.split(r"(?<=[.!?])\s+", part)
                if STATEMENT_FRAMING.search(sentence)
            ]
            if framing:
                flag(
                    exercise.key,
                    "statement_framing",
                    f"The statement frames the exercise instead of giving it, such as "
                    f"'{framing[0][:90]}'. Keep every given and task word for word and drop the "
                    "framing sentence.",
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
            found = PLAIN_MATH.search(prose) or SPOKEN_MATH.search(prose)
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
                f"{len(samples)} text(s) type mathematics as plain characters or words, such "
                f"as '{samples[0]}'. Write every symbol, variable and formula as inline LaTeX: "
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


def plain_math(value: JsonValue) -> list[str]:
    """Mathematics typed as characters or words in the rendered text of any content."""
    return [
        found[0]
        for _, text in _prose(value)
        if (found := PLAIN_MATH.search(prose := INLINE_SPANS.sub(" ", text)))
        or (found := SPOKEN_MATH.search(prose))
    ]


# A quotient written with a slash in displayed mathematics, outside units and derivatives.
_UNIT_GROUP = re.compile(r"\\(?:mathrm|text|operatorname)\{[^{}]*\}|\bd\s*/\s*d")
_SLASH = re.compile(r"[\w)}!]\s*/\s*[\\\w({]")


def slash_quotients(latex: str) -> list[str]:
    stripped = _UNIT_GROUP.sub(" ", latex)
    return [match[0] for match in _SLASH.finditer(stripped)]


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


def citation_flags(
    root: Path, state: StudyState, documents: dict[str, object]
) -> list[dict[str, JsonValue]]:
    """Cited pages past the end of their source. Only sources whose text was read (cached) are
    counted, so the check never extracts a document. `documents` maps a flag item to the
    content it covers."""
    from tum_mcp.course.sources.text import cached_record

    counts = {
        item.resource.key: len(record.pages)
        for item in state.resources
        if item.status == "current"
        and item.sha256
        and (record := cached_record(root, item.sha256)) is not None
    }
    flags: list[dict[str, JsonValue]] = []

    def visit(item: str, value: object) -> None:
        if isinstance(value, dict):
            sources, pages = value.get("sources"), value.get("pages")
            if isinstance(pages, str) and isinstance(sources, list) and sources:
                first = sources[0] if isinstance(sources[0], str) else sources[0].get("key")
                last = int(pages.rpartition("-")[2])
                if first in counts and last > counts[first]:
                    flags.append(
                        {
                            "item": item,
                            "flag": "citation_page",
                            "detail": f"Pages {pages} of '{first}' cite past its "
                            f"{counts[first]} pages.",
                        }
                    )
            for child in value.values():
                visit(item, child)
        elif isinstance(value, list):
            for child in value:
                visit(item, child)

    for item, value in documents.items():
        visit(item, value)
    return flags
