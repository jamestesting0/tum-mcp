import pytest
from pydantic import ValidationError

from tum_mcp.study_content import FormulaBlock
from tum_mcp.study_math import compile_latex, safe_mathml


@pytest.mark.parametrize(
    "latex",
    [
        r"\sum_{v\in V}\deg(v)=2|E|",
        r"d(v)=d(u)+1",
        r"\frac{-b\pm\sqrt{b^2-4ac}}{2a}",
        r"\begin{pmatrix}a&b\\c&d\end{pmatrix}",
        r"\int_0^1 x^2\,dx=\frac{1}{3}",
    ],
)
def test_latex_compiles_locally_to_inert_math(latex: str) -> None:
    markup = compile_latex(latex)
    assert 'display="block"' in markup
    assert safe_mathml(markup) == markup
    assert "<script" not in markup


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
