import pytest
from pydantic import ValidationError

from tum_mcp.study_content import FormulaBlock
from tum_mcp.study_math import compile_latex, safe_mathml


@pytest.mark.parametrize(
    "latex,element",
    [
        (r"\sum_{v\in V}\deg(v)=2|E|", "munder"),
        (r"d(v)=d(u)+1", "mi"),
        (r"\frac{-b\pm\sqrt{b^2-4ac}}{2a}", "mfrac"),
        (r"\begin{pmatrix}a&b\\c&d\end{pmatrix}", "mtable"),
        (r"\int_0^1 x^2\,dx=\frac{1}{3}", "msubsup"),
        (r"\binom{n}{k}p^k(1-p)^{n-k}", "mfrac"),
        (r"\begin{bmatrix}1&0\\0&1\end{bmatrix}", "mtable"),
    ],
)
def test_latex_compiles_locally_to_inert_math(latex: str, element: str) -> None:
    markup = compile_latex(latex)
    assert 'display="block"' in markup
    assert safe_mathml(markup) == markup
    assert f"<{element}" in markup


@pytest.mark.parametrize(
    "latex",
    [
        r"\frac{a}",
        r"\badcommand{x}",
        r"\frac{a}{b",
        r"\left(x",
        r"\text{<script>alert(1)</script>}",
        r"\href{https://example.invalid}{x}",
        r"\newcommand{\x}{\x}\x",
        "{" * 65 + "x" + "}" * 65,
    ],
)
def test_invalid_or_active_latex_is_rejected_instead_of_silently_rendering(latex: str) -> None:
    with pytest.raises(ValueError):
        compile_latex(latex)


def test_formula_accepts_latex_or_legacy_mathml_without_ambiguous_inputs() -> None:
    base = {
        "kind": "formula",
        "title": "Expression",
        "sources": ["source"],
        "plain": "x squared",
        "symbols": [{"symbol": "x", "meaning": "Variable"}],
        "conditions": "Real x.",
    }
    assert FormulaBlock.model_validate(base | {"latex": "x^2"}).latex == "x^2"
    markup = compile_latex("x^2")
    assert FormulaBlock.model_validate(base | {"mathml": markup}).mathml == markup
    for expression in ({}, {"latex": "x^2", "mathml": markup}):
        with pytest.raises(ValidationError):
            FormulaBlock.model_validate(base | expression)


def test_delimiter_bars_keep_text_size_and_only_left_right_bars_stretch() -> None:
    # \lvert and | stay text-size delimiters without operator space; \mid keeps its space.
    ket = compile_latex(r"\tfrac{1}{2}\bigl(\lvert 0\rangle\bigr)")
    assert '<mo stretchy="false" lspace="0" rspace="0">&#x0007C;</mo>' in ket
    assert '<mo stretchy="false">&#x02223;</mo>' in compile_latex(r"P(A \mid B)")
    assert 'stretchy="true"' in compile_latex(r"\left| \frac{1}{2} \right|")
    # Bare bars, the inline slash and a ket's sign label take no operator space either.
    pair = compile_latex(r"(|00\rangle + |11\rangle)/\sqrt{2}")
    assert pair.count('lspace="0" rspace="0">&#x0007C;') == 2
    assert '<mo lspace="0" rspace="0">&#x0002F;</mo>' in pair
    assert "<mi>&#x0002B;</mi><mi>&#x027E9;</mi>" in compile_latex(r"|+\rangle")
    assert "<mo>&#x0002B;</mo>" in pair
