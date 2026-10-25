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
    return safe_mathml(result)
