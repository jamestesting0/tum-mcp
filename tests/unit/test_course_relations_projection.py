"""Graph interpretation must not turn shared content into false dependencies."""

from tum_mcp.course.relations.graph import safe_text
from tum_mcp.course.relations.packet import excerpt


def test_packet_excerpts_remove_links_with_mixed_case_schemes() -> None:
    text = "Read HTTPS://example.invalid/URL_SECRET and FiLe:///private/LOCAL_SECRET afterwards."
    result = excerpt(text)
    assert "SECRET" not in result and "afterwards" in result


def test_search_text_excludes_solutions_hints_correctness_and_flashcard_backs() -> None:
    text = safe_text(
        {
            "title": "Teaching",
            "blocks": [{"paragraphs": ["Explain registration."]}],
            "solution": {"text": "SOLUTION_SECRET"},
            "hints": ["HINT_SECRET"],
            "back": "BACK_SECRET",
            "correct": "CORRECT_SECRET",
            "sources": ["PRIVATE_SOURCE"],
            "svg": "IMAGE_LITERAL",
            "code": "CODE_LITERAL",
        }
    )
    assert "Teaching" in text and "registration" in text
    assert "SECRET" not in text and "PRIVATE" not in text and "LITERAL" not in text
