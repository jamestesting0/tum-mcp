"""Graph interpretation must not turn shared content into false dependencies."""

from tum_mcp.study_knowledge_assertions import cycle_groups
from tum_mcp.study_knowledge_graph import Edge, safe_text
from tum_mcp.study_knowledge_packet import excerpt


def test_packet_excerpts_remove_links_with_mixed_case_schemes() -> None:
    text = "Read HTTPS://example.invalid/URL_SECRET and FiLe:///private/LOCAL_SECRET afterwards."
    result = excerpt(text)
    assert "SECRET" not in result and "afterwards" in result


def test_only_reviewed_prerequisites_participate_in_semantic_cycles() -> None:
    edges = {
        Edge("concept/a", "concept/b", "prerequisite_of", "reviewed", "a-b"),
        Edge("concept/b", "concept/a", "contrasts", "reviewed", "b-a"),
        Edge("unit/u", "concept/a", "teaches", "reviewed", "teaches-a"),
        Edge("unit/u", "concept/b", "teaches", "reviewed", "teaches-b"),
    }
    assert cycle_groups(edges) == {}
    edges.add(Edge("concept/b", "concept/a", "prerequisite_of", "reviewed", "back"))
    assert cycle_groups(edges) == {
        "a-b": frozenset({"a-b", "back"}),
        "back": frozenset({"a-b", "back"}),
    }


def test_deep_prerequisite_chains_do_not_depend_on_python_recursion_limit() -> None:
    edges = {
        Edge(f"concept/c{i}", f"concept/c{i + 1}", "prerequisite_of", "reviewed", f"edge-{i}")
        for i in range(1999)
    }
    assert cycle_groups(edges) == {}
    edges.add(Edge("concept/c1999", "concept/c0", "prerequisite_of", "reviewed", "back"))
    assert len(cycle_groups(edges)) == 2000


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
