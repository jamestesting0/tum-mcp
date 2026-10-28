import pytest

from tum_mcp.study_math import inline_math, validate_inline


def test_inline_code_stays_literal_and_math_beside_it_compiles() -> None:
    text = r"Match `\(\d+\)` with `re.search`, then compute \(n^2\)."
    assert inline_math(text) == ["n^2"]
    assert validate_inline(text) == text


def test_stray_math_delimiters_outside_inline_code_are_still_rejected() -> None:
    with pytest.raises(ValueError, match="matching"):
        validate_inline(r"Use `x` and \( unclosed")
