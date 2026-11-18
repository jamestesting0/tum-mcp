import pytest
from pydantic import ValidationError

from tum_mcp.course.content.terms import TermList

TERMS = TermList.model_validate(
    {
        "pairs": [
            {"en": ["regular language", "regular languages"], "de": "reguläre Sprache"},
            {"en": "language", "de": "Sprache"},
            {"en": "Pumping-Lemma", "de": "Pumping-Lemma"},
        ],
        "glosses": [{"term": "pigeonhole", "meaning": "Too many items for too few boxes."}],
    }
)


def mark(*paragraphs: str, field: str = "paragraphs") -> list[str]:
    context = {"blocks": [{"kind": "text", field: list(paragraphs), "title": paragraphs[0]}]}
    TERMS.marker().mark(context)
    return context["blocks"][0][field]


def test_the_longest_listed_form_wins_and_each_term_is_marked_once() -> None:
    assert mark("Every regular language is a language.", "Regular languages again.") == [
        "Every {{regular language}} is a {{language}}.",
        "Regular languages again.",
    ]


def test_marking_skips_compounds_code_math_and_existing_markers() -> None:
    assert mark("A Sprach-Test uses `language` and \\(language\\); {{Sprache}} then language.") == [
        "A Sprach-Test uses `language` and \\(language\\); {{Sprache}} then language."
    ]


def test_only_prose_fields_are_marked() -> None:
    context = {"title": "pigeonhole", "choices": ["pigeonhole"], "explanation": "A pigeonhole."}
    TERMS.marker().mark(context)
    assert context == {
        "title": "pigeonhole",
        "choices": ["pigeonhole"],
        "explanation": "A {{pigeonhole}}.",
    }


def test_a_term_spelled_alike_in_both_languages_gets_no_bubble() -> None:
    assert mark("The Pumping-Lemma holds.") == ["The Pumping-Lemma holds."]
    bubbles = TERMS.bubbles()
    assert "pumping-lemma" not in bubbles
    assert bubbles["regular languages"] == {"pair": {"de": "reguläre Sprache"}}
    assert bubbles["reguläre sprache"] == {"pair": {"en": "regular language"}}
    assert bubbles["pigeonhole"] == {"meaning": "Too many items for too few boxes."}


def test_a_form_belongs_to_one_pair_and_a_pair_needs_two_languages() -> None:
    with pytest.raises(ValidationError, match="one pair only"):
        TermList.model_validate({"pairs": [{"en": "set", "de": "Menge"}, {"en": "set", "fr": "x"}]})
    with pytest.raises(ValidationError, match="two languages"):
        TermList.model_validate({"pairs": [{"en": "set"}]})
