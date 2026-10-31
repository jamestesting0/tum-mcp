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
