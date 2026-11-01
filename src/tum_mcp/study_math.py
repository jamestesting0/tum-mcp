"""Compile bounded LaTeX locally; only inert, validated MathML reaches the browser."""

import re
from functools import lru_cache
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from latex2mathml import exceptions
from latex2mathml.converter import convert

MATH_NS = "http://www.w3.org/1998/Math/MathML"
MATH_TAGS = set(
    "math mrow mi mn mo mtext mfrac msqrt mroot msub msup msubsup mtable mtr mtd "
    "munder mover munderover mmultiscripts mprescripts none mspace mstyle menclose".split()
)
MATH_ATTRS = {
    "display",
    # \left and \right mark their fences prefix and postfix.
    "form",
    "mathvariant",
    "displaystyle",
    "stretchy",
    "linethickness",
    "fence",
    "separator",
    "accent",
    "accentunder",
    "notation",
    "columnalign",
    "rowalign",
    "columnspacing",
    "rowspacing",
    "columnlines",
    "rowlines",
    "scriptlevel",
    "width",
    "height",
    "depth",
    "lspace",
    "rspace",
    "minsize",
    "maxsize",
}
PARSE_ERRORS = (
    exceptions.NumeratorNotFoundError,
    exceptions.DenominatorNotFoundError,
    exceptions.ExtraLeftOrMissingRightError,
    exceptions.MissingSuperScriptOrSubscriptError,
    exceptions.DoubleSubscriptsError,
    exceptions.DoubleSuperscriptsError,
    exceptions.NoAvailableTokensError,
    exceptions.InvalidStyleForGenfracError,
    exceptions.MissingEndError,
    exceptions.InvalidAlignmentError,
    exceptions.InvalidWidthError,
    exceptions.LimitsMustFollowMathOperatorError,
    ValueError,
    IndexError,
    StopIteration,
)


def safe_mathml(value: str) -> str:
    try:
        root = fromstring(value)
    except (ParseError, DefusedXmlException):
        raise ValueError("Formula must be safe, valid MathML.") from None
    if root.tag != f"{{{MATH_NS}}}math":
        raise ValueError("Formula requires the MathML math namespace.")
    arity = {
        "mfrac": 2,
        "mroot": 2,
        "msub": 2,
        "msup": 2,
        "msubsup": 3,
        "munder": 2,
        "mover": 2,
        "munderover": 3,
    }
    for element in root.iter():
        if not element.tag.startswith(f"{{{MATH_NS}}}"):
            raise ValueError("Every formula element requires the MathML namespace.")
        tag = element.tag.removeprefix(f"{{{MATH_NS}}}")
        if tag not in MATH_TAGS or not set(element.attrib) <= MATH_ATTRS:
            raise ValueError("Formula contains unsupported elements or attributes.")
        if tag in arity and len(element) != arity[tag]:
            raise ValueError("Formula has an incomplete mathematical expression.")
        if "\\" in (element.text or ""):
            raise ValueError("Formula contains an unsupported LaTeX command.")
    return value


@lru_cache(maxsize=256)
def compile_latex(value: str) -> str:
    if not value.strip() or len(value) > 5000:
        raise ValueError("LaTeX must contain 1–5000 characters.")
    # A single backslash in JSON turns \theta into a tab and \rangle into a carriage return.
    if control := re.search(r"[\x00-\x08\x09\x0b-\x1f]", value):
        raise ValueError(
            f"LaTeX holds the control character {control.group(0)!r}: write each backslash "
            "twice in JSON (\\\\theta, \\\\rangle)."
        )
    if re.search(
        r"\\(?:def|gdef|edef|let|newcommand|renewcommand|input|include|href|url|html\w*|require|write|csname)\b",
        value,
    ):
        raise ValueError("Use mathematical LaTeX without macros, files or links.")
    depth = 0
    for group in re.findall(r"\\.|[{}]", value):
        depth += (group == "{") - (group == "}")
        if depth < 0 or depth > 64:
            raise ValueError("LaTeX has unbalanced or excessive grouping.")
    if depth:
        raise ValueError("LaTeX has unbalanced grouping.")
    try:
        result = convert(value, display="block")
    except PARSE_ERRORS:
        raise ValueError("Cannot compile this LaTeX expression.") from None
    # \lvert, \vert, \| and \mid keep their text size, as in TeX and KaTeX; only \left and \right
    # (which carry stretchy="true") grow. Browsers otherwise stretch them to a whole fraction.
    # A bare bar is a delimiter (|0>, |a|, P(A|B)) and a slash divides inline, so neither takes
    # operator space, as in TeX; \mid keeps its own. Browsers otherwise space "( | 00>".
    result = DELIMITER_BAR.sub(r'<mo stretchy="false" lspace="0" rspace="0">\1</mo>', result)
    result = SOLIDUS.sub('<mo lspace="0" rspace="0">&#x0002F;</mo>', result)
    # A sign that labels a ket or bra (|+>, <-|) is part of the label, not an operator.
    result = KET_SIGN.sub(r"\1<mi>\2</mi>\3", result)
    result = BRA_SIGN.sub(r"\1<mi>\2</mi>\3", result)
    return safe_mathml(RELATION_BAR.sub(r'<mo stretchy="false">\1</mo>', result))


DELIMITER_BAR = re.compile(r'<mo(?: stretchy="false")?>(&#x0007C;|&#x02016;)</mo>')
RELATION_BAR = re.compile(r"<mo>(&#x02223;|&#x02225;)</mo>")
SOLIDUS = re.compile(r"<mo>&#x0002F;</mo>")
KET_SIGN = re.compile(
    r'(<mo stretchy="false" lspace="0" rspace="0">&#x0007C;</mo>)<mo>(&#x0002B;|&#x02212;)</mo>'
    r"(<mi>&#x027E9;</mi>)"
)
BRA_SIGN = re.compile(
    r"(<mi>&#x027E8;</mi>)<mo>(&#x0002B;|&#x02212;)</mo>"
    r'(<mo stretchy="false" lspace="0" rspace="0">&#x0007C;</mo>)'
)


# Inline code `...` and inline math \( ... \), scanned left to right as the app does, so
# text inside backticks stays literal code even when it contains \( or \).
INLINE_SPANS = re.compile(r"`[^`\n]+`|\\\((.*?)\\\)", re.DOTALL)


def inline_math(value: str) -> list[str]:
    """The inline LaTeX expressions of a text, outside inline code."""
    return [match[1] for match in INLINE_SPANS.finditer(value) if match[1] is not None]


def validate_inline(value: str) -> str:
    """Inline delimiters are explicit, so currency and literal code stay untouched."""
    for expression in inline_math(value):
        compile_latex(expression)
    remaining = INLINE_SPANS.sub("", value)
    if r"\(" in remaining or r"\)" in remaining:
        raise ValueError("Inline LaTeX needs matching \\( and \\) delimiters.")
    return value


# Variable meanings: a formula marks a listed variable wherever it is spelled as listed. The app
# mirrors these rules in mathml.mjs (markSymbols); tests/fixtures/symbol_marks.json pins both.
_TEXTUAL = {
    "text",
    "textrm",
    "textbf",
    "textit",
    "textsf",
    "texttt",
    "mathrm",
    "operatorname",
    "mbox",
    "begin",
    "end",
}
_DELIMITER_PREFIX = re.compile(r"\\(?:left|right|middle|[bB]igg?[lrm]?)$")


def symbol_latex(symbol: str) -> str:
    """A variable as written in a meaning list, `\\(\\rho\\)` or `\\rho`, as plain LaTeX."""
    text = symbol.strip()
    inner = re.fullmatch(r"\\\((.*)\\\)", text, re.S)
    return (inner.group(1) if inner else text).strip()


# A decoration makes a different variable: \(K_j^\dagger\) is not \(K_j\), \(\bar a\) is not
# \(a\). Such a form is never marked with the plain variable's meaning.
_DECORATIONS = {r"\dagger", "*", r"\ast", "T", r"\top", r"\intercal", r"\prime", r"\star"}
_ACCENTS = r"bar|hat|tilde|vec|dot|ddot|check|breve|acute|grave|mathring|overline|widehat|widetilde"
_ACCENT = re.compile(rf"\\(?:{_ACCENTS})(?![A-Za-z])\s*")


def normalize_symbol(symbol: str) -> str:
    """A listed variable as compared: no spaces (but one ending a command before a letter),
    and a script or accent argument of one character or command without braces, so `p_{i}`
    and `p_i`, `K^{\\dagger}` and `K^\\dagger`, `\\bar{a}` and `\\bar a` are the same."""
    text = re.sub(rf"(\\(?:{_ACCENTS}))\s*\{{([A-Za-z0-9])\}}", r"\1 \2", symbol_latex(symbol))
    text = re.sub(r"(\\[A-Za-z]+)\s+(?=[A-Za-z])", "\\1\x00", text)
    text = re.sub(r"\s+", "", text).replace("\x00", " ")
    return re.sub(r"([_^])\{([A-Za-z0-9]|\\[A-Za-z]+)\}", r"\1\2", text)


def _group_end(latex: str, opening: int) -> int:
    depth, index = 0, opening
    while index < len(latex):
        char = latex[index]
        if char == "\\":
            index += 2
            continue
        depth += (char == "{") - (char == "}")
        index += 1
        if depth == 0:
            return index
    return len(latex)


def _skip_space(latex: str, position: int) -> int:
    while position < len(latex) and latex[position].isspace():
        position += 1
    return position


def _match_at(latex: str, start: int, symbol: str) -> int:
    position, k = start, 0
    while k < len(symbol):
        want = symbol[k]
        if want == " ":
            # `\bar a` also matches `\bar{a}`.
            if latex[position : position + 1] == "{" and latex[position + 2 : position + 3] == "}":
                if latex[position + 1 : position + 2] != symbol[k + 1 : k + 2]:
                    return -1
                position, k = position + 3, k + 2
                continue
            if position >= len(latex) or not latex[position].isspace():
                return -1
            position, k = _skip_space(latex, position), k + 1
            continue
        if position > start:
            position = _skip_space(latex, position)
        if want in "_^" and latex[position : position + 1] == want:
            position, k = _skip_space(latex, position + 1), k + 1
            if latex[position : position + 1] == "{":
                # A braced script matches the listed one written without braces.
                end = _group_end(latex, position)
                inner = latex[position + 1 : end - 1].strip()
                if inner and symbol.startswith(inner, k) and symbol[k : k + 1] != "{":
                    position, k = end, k + len(inner)
            continue
        if latex[position : position + 1] != want:
            return -1
        position, k = position + 1, k + 1
    if re.search(r"\\[A-Za-z]+$", symbol) and latex[position : position + 1].isalpha():
        return -1
    return position


def _script_end(latex: str, at: int) -> int:
    position = _skip_space(latex, at + 1)
    if latex[position : position + 1] == "{":
        return _group_end(latex, position)
    command = re.match(r"\\[A-Za-z]+|\\.", latex[position:])
    return position + (len(command.group(0)) if command else 1)


def _decoration_end(latex: str, at: int) -> int:
    """The end of a dagger, star, transpose or prime decorating the variable before `at`."""
    if latex[at : at + 1] == "'":
        return len(latex) - len(latex[at:].lstrip("'"))
    if latex[at : at + 1] != "^":
        return -1
    end = _script_end(latex, at)
    script = latex[at + 1 : end].strip()
    if script.startswith("{") and script.endswith("}"):
        script = script[1:-1].strip()
    return end if script in _DECORATIONS or set(script) == {"'"} else -1


def _scan(latex: str, symbols: list[str]) -> tuple[list[tuple[int, int, int]], list[str]]:
    order = sorted(
        ((index, normalize_symbol(text)) for index, text in enumerate(symbols)),
        key=lambda item: -len(item[1]),
    )
    marks: list[tuple[int, int, int]] = []
    variants: list[str] = []
    position, previous = 0, ""
    while position < len(latex):
        textual = re.match(r"\\([A-Za-z]+)\s*\{", latex[position:])
        if textual and textual.group(1) in _TEXTUAL:
            end = _group_end(latex, position + textual.end() - 1)
            previous, position = latex[position:end], end
            continue
        hit = None
        if not latex[position].isspace() and not _DELIMITER_PREFIX.search(previous):
            hit = next(
                (
                    (index, symbol, end)
                    for index, symbol in order
                    if symbol and (end := _match_at(latex, position, symbol)) >= 0
                ),
                None,
            )
        accent = None if hit else _ACCENT.match(latex, position)
        if hit:
            index, symbol, end = hit
            after = _skip_space(latex, end)
            if (decorated := _decoration_end(latex, after)) >= 0:
                variants.append(latex[position:decorated])
                previous, position = latex[position:decorated], decorated
                continue
            tail = re.search(r"([_^])[^_^]*$", symbol)
            if tail and latex[after : after + 1] in ("_", "^") and latex[after] != tail.group(1):
                end = _script_end(latex, after)
            marks.append((position, end, index))
            previous, position = latex[position:end], end
            continue
        if accent:
            start = accent.end()
            end = _group_end(latex, start) if latex[start : start + 1] == "{" else start
            if end == start:
                token = re.match(r"\\[A-Za-z]+|\\.|.", latex[start:], re.S)
                end = start + (len(token.group(0)) if token else 0)
            if _scan(latex[start:end], symbols)[0]:
                variants.append(latex[position:end])
            previous, position = latex[position:end], end
            continue
        token = re.match(r"\\[A-Za-z]+|\\.|.", latex[position:], re.S)
        step = token.group(0) if token else latex[position]
        if not step.isspace():
            previous = step
        position += len(step)
    return marks, variants


def symbol_marks(latex: str, symbols: list[str]) -> list[tuple[int, int, int]]:
    """Where each listed variable occurs: (start, end, index), longest listed variable first.
    Text arguments, environment names and delimiters after \\left are never marked; a
    subscripted match keeps a following non-decorating superscript (and the reverse); a
    decorated form (K_j^\\dagger, x^*, x', \\bar a) is a different variable and stays unmarked
    unless it is listed itself."""
    return _scan(latex, symbols)[0]


def decorated_variants(latex: str, symbols: list[str]) -> list[str]:
    """Decorated forms of listed variables that are not listed themselves, as written."""
    return _scan(latex, symbols)[1]


def symbol_occurs(latex: str, symbol: str) -> bool:
    return any(index == 0 for _, _, index in symbol_marks(latex, [symbol]))


# One reading of a formula's top level, the same as the app's topTokens in mathml.mjs (the
# shared cases are tests/fixtures/latex_scan.json): depth counts braces, brackets,
# \left...\right pairs and environments; an angle bracket groups only as an inner product,
# since a bra \langle\psi| never closes.
_OPENS = {"{", "lbrace", "lfloor", "lceil", "left", "begin"}
_CLOSES = {"}", "rbrace", "rfloor", "rceil", "right", "end"}
_TOKEN = re.compile(r"\\(?:[A-Za-z]+|.)|.", re.DOTALL)
_BAR = re.compile(r"\||\\vert|\\mid")
_SPACING = re.compile(r"(?:\s|~|\\[,:;! ]|\\q?quad(?![A-Za-z]))+")
_CONNECTIVES = {
    r"\iff", r"\implies", r"\impliedby", r"\Rightarrow", r"\Leftrightarrow",
    r"\Longrightarrow", r"\Longleftrightarrow",
}  # fmt: skip
RELATIONS = {
    r"\Longleftrightarrow", r"\Longrightarrow", r"\longrightarrow", r"\longmapsto",
    r"\Leftrightarrow", r"\Rightarrow", r"\rightarrow", r"\mapsto", r"\implies", r"\coloneqq",
    r"\cong", r"\simeq", r"\approx", r"\propto", r"\equiv", r"\leq", r"\geq", r"\neq", r"\iff",
    r"\sim", r"\subseteq", r"\supseteq", r"\subset", r"\supset", r"\leftarrow", r"\Leftarrow",
    r"\gets", r"\models", r"\vdash", r"\vDash", r"\ne", r"\le", r"\ge", r"\to", "=", "<", ">",
}  # fmt: skip


def top_tokens(latex: str) -> list[tuple[int, str, int]]:
    r"""Each token with its start and the depth it sits at; kets |a, b\rangle, bras
    \langle a, b| and inner products \langle u, v\rangle are groups too."""
    tokens: list[tuple[int, str, int]] = []
    stack: list[str] = []
    previous = ""

    def ket(index: int) -> bool:
        rest = latex[index + 1 :]
        close, bar = rest.find(r"\rangle"), _BAR.search(rest)
        return close >= 0 and (bar is None or close < bar.start())

    for match in _TOKEN.finditer(latex):
        index, piece = match.start(), match.group()
        tokens.append((index, piece, len(stack)))
        if piece.isspace():
            continue
        delimiter, previous = _DELIMITER_PREFIX.search(previous) is not None, piece
        if delimiter:
            continue  # the delimiter after \left or \right belongs to that pair
        if len(piece) > 1:
            name = piece[1:]
            if name in _OPENS:
                stack.append("group")
            elif name in _CLOSES:
                stack[-1:] = []
            elif name == "langle":
                stack.append("angle" if ket(index) else "bra")
            elif name == "rangle" and stack[-1:] in (["angle"], ["ket"]):
                stack.pop()
        elif piece == "|":
            if stack[-1:] == ["bra"]:
                stack.pop()
            if ket(index):
                stack.append("ket")
        elif piece in "{([":
            stack.append("group")
        elif piece in "})]":
            stack[-1:] = []
    return tokens


def formula_parts(latex: str) -> list[str]:
    """The statements a formula lists, cut where the app may break its line."""
    parts, start = [], 0
    for index, piece, depth in top_tokens(latex):
        if depth or index < start:
            continue
        end = (
            index
            if re.fullmatch(r"\\q?quad", piece) or (index > start and piece in _CONNECTIVES)
            else index + 1
            if piece == ","
            else None
        )
        if end is not None:
            if text := latex[start:end].strip():
                parts.append(text)
            space = _SPACING.match(latex, end)
            start = space.end() if space else end
    if last := latex[start:].strip():
        parts.append(last)
    return parts


def split_relation(latex: str) -> tuple[str, str, str]:
    """A derivation line split at its first top-level relation, which the app aligns on."""
    for index, piece, depth in top_tokens(latex):
        if not depth and piece in RELATIONS:
            return latex[:index], piece, latex[index + len(piece) :]
    return "", "", latex
