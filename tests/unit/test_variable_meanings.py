import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.course.checks.report import (
    echoed_meanings,
    generic_meanings,
    redeclared_meanings,
    renamed_meanings,
    typed_math_labels,
    unexplained_variables,
)
from tum_mcp.course.content.exam import CompactFormula
from tum_mcp.course.content.latex import symbol_marks, validate_inline
from tum_mcp.course.content.study import DerivationBlock, resolve_meanings

CASES = json.loads((Path(__file__).parents[1] / "fixtures/symbol_marks.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["latex"] for case in CASES])
def test_variables_are_marked_where_spelled_and_nowhere_else(case: dict) -> None:
    # The app's markSymbols runs the same table in test_course_app_math_browser.
    marks = symbol_marks(case["latex"], case["symbols"])
    assert [[case["latex"][start:end], index] for start, end, index in marks] == case["marks"]


def derivation(*lines: str, symbols: list[dict] | None = None) -> dict:
    return {
        "kind": "derivation",
        "sources": ["s"],
        "groups": [{"lines": [{"latex": line} for line in lines]}],
        "symbols": symbols or [],
    }


def meaning(symbol: str, text: str = "density operator of the ensemble") -> dict:
    return {"symbol": symbol, "meaning": text}


def test_a_meaning_must_name_a_variable_its_formula_spells_once() -> None:
    DerivationBlock.model_validate(
        derivation(r"\rho=\sum_i p_i P_i", symbols=[meaning(r"\(p_{i}\)")])
    )
    with pytest.raises(ValidationError, match="does not appear in its formula"):
        DerivationBlock.model_validate(
            derivation(r"|\psi\rangle", symbols=[meaning(r"\lvert\psi\rangle")])
        )
    with pytest.raises(ValidationError, match="twice"):
        DerivationBlock.model_validate(
            derivation(r"p_i", symbols=[meaning(r"p_i"), meaning(r"p_{i}")])
        )


def test_a_meaning_reaches_every_formula_of_its_context_and_no_other() -> None:
    first = derivation(r"\rho=\sum_i p_i P_i", symbols=[meaning(r"\(\rho\)")])
    later = derivation(r"\operatorname{Tr}\rho=1")
    own = derivation(r"\rho=0", symbols=[meaning(r"\(\rho\)", "the zero state here")])
    applied = {"math": [r"\rho\ge 0"]}
    exercise = {"steps": [first, later, own, applied]}
    other = {"steps": [derivation(r"\rho=1")]}
    resolve_meanings(exercise)
    resolve_meanings(other)
    assert later["symbols"] == [meaning(r"\(\rho\)")]
    assert applied["symbols"] == [meaning(r"\(\rho\)")]
    assert own["symbols"] == [meaning(r"\(\rho\)", "the zero state here")]
    assert other["steps"][0]["symbols"] == []


def test_report_prompts_for_unexplained_renamed_and_echoed_meanings() -> None:
    unit = {
        "blocks": [
            derivation(
                r"\rho_A=\operatorname{Tr}_B\rho", r"x_i=\theta", symbols=[meaning(r"\(\rho\)")]
            ),
            {"kind": "text", "paragraphs": [r"Each \(x_i\) is a sample."]},
        ]
    }
    # rho_A and theta are explained nowhere; x_i is mentioned in the text.
    assert unexplained_variables(unit) == [r"\rho_A", r"\theta"]
    assert renamed_meanings({"math": ["p"], "symbols": [meaning("p", "the p")]}) == ["p"]
    echoed = {
        "math": ["p_i"],
        "text": "Here p_i is the chance of state i.",
        "symbols": [meaning("p_i", "chance of state i")],
    }
    assert echoed_meanings(echoed) == ["p_i"]
    assert (
        echoed_meanings({"math": ["p_i"], "symbols": [meaning("p_i", "chance of state i")]}) == []
    )


@pytest.mark.parametrize("broken", ["\\(|1\rangle\\)", "\\(\theta\\)"])
def test_latex_with_a_json_escape_control_character_is_rejected(broken: str) -> None:
    # "\\rangle" and "\\theta" written with one backslash in JSON become CR and TAB.
    with pytest.raises(ValueError, match="control character"):
        validate_inline(broken)


def test_a_meaning_written_again_in_the_same_context_is_flagged() -> None:
    pattern = {
        "steps": [
            {"math": ["h(x)=0"], "symbols": [meaning(r"\(h(x)\)", "two-bit hash")]},
            {"math": ["h(x)=1"], "symbols": [meaning(r"\(h(x)\)", "Two-bit  hash")]},
        ]
    }
    assert redeclared_meanings(pattern) == ["h(x)"]


def test_a_decorated_variable_needs_its_own_meaning() -> None:
    # K_j^\dagger is the adjoint, not the Kraus operator; the app must not show K_j's meaning.
    context = {
        "steps": [
            {
                "math": [r"\sum_jK_j^\dagger K_j=I"],
                "symbols": [meaning(r"\(K_j\)", "Kraus operator")],
            }
        ]
    }
    assert unexplained_variables(context) == [r"K_j^\dagger"]
    with pytest.raises(ValidationError, match="no meaning of its own"):
        CompactFormula(
            latex=r"\sum_jK_j^\dagger K_j=I",
            plain="The Kraus operators are complete.",
            symbols=[{"symbol": r"\(K_j\)", "meaning": "Kraus operator"}],
        )


def test_a_task_quantity_needs_a_meaning_and_a_specific_one() -> None:
    context = {
        "math": [r"P_k=\sin^2((2k+1)\theta)"],
        "symbols": [
            meaning(r"\(P_k\)", "Success probability"),
            meaning(r"\(\theta\)", "Rotation angle"),
        ],
    }
    assert unexplained_variables(context) == []
    assert unexplained_variables(context, task=True) == ["k"]
    legend = {
        "symbols": [
            meaning(r"\(N, M, k\)", "Given quantities."),
            meaning(r"\(N\)", "Number of records"),
        ]
    }
    assert generic_meanings(legend) == [r"\(N, M, k\)"]


def test_figure_labels_write_mathematics_as_latex() -> None:
    from tum_mcp.course.content.figures import safe_svg

    figure = '<svg viewBox="0 0 200 100"><text x="10" y="40">{}</text></svg>'
    # Typed subscripts and kets render in the text font, unlike the typeset math around them.
    context = {"kind": "figure", "svg": figure.format("x₃") + figure.format("|1⟩")}
    assert typed_math_labels(context) == ["x₃", "|1⟩"]
    assert typed_math_labels({"kind": "figure", "svg": figure.format(r"\(x_3\)")}) == []
    safe_svg(figure.format(r"\(x_3\)"))
    with pytest.raises(ValueError, match="wholly as inline LaTeX"):
        safe_svg(figure.format(r"wire \(x_3\)"))
