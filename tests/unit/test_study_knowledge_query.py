"""Retrieval invariants independent of any particular course serialization."""

from types import SimpleNamespace

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.study_knowledge_graph import Edge, Graph, Node
from tum_mcp.study_knowledge_packet import encoded, excerpt, fit
from tum_mcp.study_knowledge_query import lexical_score, seeds, walk


def node(ref, title="Topic", body="", workspace="study", payload=None):
    return Node(ref, workspace, "unit", title, "", body, payload or {})


def test_word_matching_prefers_titles_and_normalizes_unicode():
    value = node("study/unit/one", "Ｆｕｎｃｔｉｏｎ", "composition")
    assert lexical_score(value, "function COMPOSITION") == 5
    assert lexical_score(value, "function missing") == 4
    assert lexical_score(value, "funct") == 0


def test_alias_collision_is_explicit_without_arbitrary_selection():
    graph = Graph(None)
    for key in ("a", "b"):
        graph.add(node(f"concept/{key}", workspace="concept", payload={"aliases": ["Shared"]}))
    assert seeds(graph, "shared") == ([], ["concept/a", "concept/b"])


def test_navigation_never_bridges_shared_source_or_sibling_parent():
    graph = Graph(None)
    graph.nodes = {ref: node(ref) for ref in ("a", "parent", "b", "source/common")}
    graph.edges = {
        Edge("parent", "a", "contains"),
        Edge("parent", "b", "contains"),
        Edge("a", "source/common", "supported_by"),
        Edge("b", "source/common", "supported_by"),
    }
    routes, exhausted = walk(graph, ["a"], SimpleNamespace(edge=lambda _: True))
    assert set(routes) == {"a", "parent"} and not exhausted


def test_reverse_navigation_preserves_fact_direction_and_stops_at_two_hops():
    graph = Graph(None)
    graph.edges = {
        Edge("a", "b", "prerequisite_of"),
        Edge("b", "c", "prerequisite_of"),
        Edge("c", "d", "prerequisite_of"),
    }
    routes, _ = walk(graph, ["c"], SimpleNamespace(edge=lambda _: True))
    assert routes["a"][0][0][0].start == "b"
    assert routes["a"][0][0][1] == "reverse"
    assert len(routes["a"][0]) == 2


def test_traversal_node_and_edge_exhaustion_are_reported():
    graph = Graph(None)
    graph.edges = {Edge("a", str(i), "teaches") for i in range(2200)}
    routes, exhausted = walk(graph, ["a"], SimpleNamespace(edge=lambda _: True))
    assert exhausted and len(routes) == 256


def test_utf8_packet_budget_drops_complete_units_and_paths():
    packet = {
        "items": [{"id": "first", "excerpt": "語" * 300}, {"id": "last", "excerpt": "語" * 300}],
        "paths": [
            {"target": "first", "nodes": ["first", "nav"]},
            {"target": "last", "nodes": ["last", "other"]},
        ],
        "nodes": [{"id": "nav"}, {"id": "other"}],
        "issues": [],
        "omitted": {},
        "status": "ok",
        "truncation": {},
        "direct": ["first", "last"],
    }
    result = fit(packet, 2048)
    assert len(encoded(result)) <= 2048
    assert result["items"] and result["truncation"]["output_budget"]
    ids = {item["id"] for item in result["items"] + result["nodes"]}
    assert all(set(path["nodes"]) <= ids for path in result["paths"])
    assert set(result["direct"]) <= ids
    assert len(excerpt("語" * 200).encode()) <= 400
    assert "https://secret" not in excerpt("Read https://secret.invalid/token.")


def test_oversized_minimum_envelope_is_an_error():
    with pytest.raises(CampusError, match="envelope"):
        fit(
            {"items": [], "issues": [], "status": "ok", "truncation": {}, "private": "x" * 5000},
            2048,
        )


def test_conversational_multi_concept_query_finds_existing_homes():
    graph = Graph(None)
    graph.add(
        node("study/unit/vacuum", "Vacuum cleaner world", "Partially observable environment.")
    )
    graph.add(
        node("study/unit/transitions", "Deterministic transitions", "A fixed transition rule.")
    )
    selected, ambiguous = seeds(
        graph, "Explain the vacuum cleaner observability deterministic please"
    )
    assert set(selected) == {"study/unit/vacuum", "study/unit/transitions"}
    assert not ambiguous
    assert seeds(graph, "Please explain the quuxnebula") == ([], [])


def test_polite_query_does_not_resolve_a_shared_alias_arbitrarily():
    graph = Graph(None)
    for key, title in (("observer", "Observer"), ("coupling", "Loose coupling")):
        graph.add(
            node(
                f"concept/{key}",
                title,
                "Notification pattern",
                "concept",
                {"aliases": ["Notification pattern"]},
            )
        )
    assert seeds(graph, "Please explain the notification pattern") == (
        [],
        ["concept/coupling", "concept/observer"],
    )
    assert seeds(graph, "notification pattern exam") == ([], [])
    assert seeds(graph, "Observer notification pattern exam")[0] == ["concept/observer"]


def test_partial_body_match_needs_distinct_terms_without_matching_a_substring():
    value = node("study/unit/one", "Theory", "composition registration")
    assert lexical_score(value, "composition missing") == 0
    assert lexical_score(value, "composition registration missing") == 2
    assert lexical_score(value, "composit") == 0
