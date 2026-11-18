import pytest
from pydantic import ValidationError

from tum_mcp.course.checks.report import missing_pair_flags
from tum_mcp.course.content.terms import TermList

TERMS = TermList.model_validate(
    {
        "pairs": [
            {"en": ["regular language", "regular languages"], "de": "reguläre Sprache"},
            {"en": "language", "de": "Sprache"},
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


def test_bubbles_show_the_other_language_and_the_gloss() -> None:
    bubbles = TERMS.bubbles()
    assert bubbles["regular languages"] == {"pair": {"de": "reguläre Sprache"}}
    assert bubbles["reguläre sprache"] == {"pair": {"en": "regular language"}}
    assert bubbles["pigeonhole"] == {"meaning": "Too many items for too few boxes."}


def test_bullet_points_steps_and_table_cells_are_marked() -> None:
    context = {"points": ["A language."], "steps": ["A pigeonhole."], "rows": [["Sprache"]]}
    TERMS.marker().mark(context)
    assert context == {
        "points": ["A {{language}}."],
        "steps": ["A {{pigeonhole}}."],
        "rows": [["Sprache"]],
    }


def test_a_form_belongs_to_one_pair_and_a_pair_needs_two_languages() -> None:
    with pytest.raises(ValidationError, match="one pair only"):
        TermList.model_validate({"pairs": [{"en": "set", "de": "Menge"}, {"en": "set", "fr": "x"}]})
    with pytest.raises(ValidationError, match="two languages"):
        TermList.model_validate({"pairs": [{"en": "set"}]})
    with pytest.raises(ValidationError, match="spelled the same"):
        TermList.model_validate({"pairs": [{"en": "Pumping-Lemma", "de": "Pumping-Lemma"}]})


def test_a_workspace_in_another_language_than_the_student_needs_pairs() -> None:
    present = {"study": True, "exercises": False}
    # German Study for a student who writes in English, with no pairs yet.
    flags = missing_pair_flags(
        TermList(), {"study": "de", "exercises": "de"}, ("en", "de"), present
    )
    assert [(flag["flag"], "study" in str(flag["detail"])) for flag in flags] == [
        ("missing_pairs", True)
    ]
    assert not missing_pair_flags(TERMS, {"study": "de"}, ("en", "de"), present)
    assert not missing_pair_flags(TermList(), {"study": "de"}, ("de", "de"), present)
    assert not missing_pair_flags(TermList(), {"study": "de"}, (None, "de"), present)
