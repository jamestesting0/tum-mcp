"""Deterministic two-hop retrieval over one local optimistic course snapshot."""

import re
from collections import deque
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_knowledge_assertions import AssertionChecks
from tum_mcp.study_knowledge_evidence import EvidenceChecks
from tum_mcp.study_knowledge_graph import Edge, Graph, Node
from tum_mcp.study_knowledge_models import Purpose, normalized
from tum_mcp.study_knowledge_packet import envelope, excerpt, fit, item_view
from tum_mcp.study_knowledge_projection import project
from tum_mcp.study_knowledge_store import load_inputs

LEARNING = frozenset({"study", "exercises", "exam", "lectures"})
NAVIGATION = frozenset({"supported_by", "coverage_of", "covered_by"})


def tokens(value: str) -> frozenset[str]:
    return frozenset(re.findall(r"[^\W_]+", normalized(value)))


SCAFFOLD = frozenset(
    "a an and are as at be by can could do does explain for from how i in is it me of on "
    "or please show that the these this to was what when where which with would you".split()
)


def _lexical(node: Node, wanted: frozenset[str]) -> tuple[int, int]:
    title, summary, body = (
        tokens(value) & wanted for value in (node.title, node.summary, node.body)
    )
    covered = title | summary | body
    if not wanted or not (title or summary or len(body) >= min(2, len(wanted))):
        return 0, 0
    return 4 * len(title) + 2 * len(summary) + len(body), len(covered)


def lexical_score(node: Node, query: str) -> int:
    return _lexical(node, tokens(query) - SCAFFOLD)[0]


def seeds(graph: Graph, query: str) -> tuple[list[str], list[str]]:
    value = normalized(query)
    exact = [
        node.id
        for node in graph.nodes.values()
        if node.workspace in LEARNING | {"concept"}
        and value in {normalized(node.id), normalized(node.id.rsplit("/", 1)[-1])}
    ]
    if exact:
        return sorted(exact)[:8], []
    names: dict[str, list[str]] = {}
    labels: dict[str, set[str]] = {}
    for node in graph.nodes.values():
        if node.workspace != "concept":
            continue
        aliases = node.payload.get("aliases", []) if isinstance(node.payload, dict) else []
        labels[node.id] = {normalized(node.title), *(normalized(a) for a in aliases)}
        for name in labels[node.id]:
            names.setdefault(name, []).append(node.id)
    aliases = names.get(value, [])
    if aliases:
        return ([], sorted(aliases)) if len(aliases) > 1 else (aliases, [])
    exact_titles = [
        node.id
        for node in graph.nodes.values()
        if node.workspace in LEARNING and normalized(node.title) == value
    ]
    if exact_titles:
        return sorted(exact_titles)[:8], []
    words = [word for word in re.findall(r"[^\W_]+", value) if word not in SCAFFOLD]
    filtered = " ".join(words)
    wanted = frozenset(words)
    aliases = names.get(filtered, [])
    if aliases:
        return ([], sorted(aliases)) if len(aliases) > 1 else (aliases, [])
    scored = []
    for node in graph.nodes.values():
        if node.workspace not in LEARNING | {"concept"}:
            continue
        if node.workspace == "concept":
            collided = {name for name in labels[node.id] if len(names[name]) > 1}
            alias_words = frozenset(word for name in collided for word in tokens(name))
            unique_phrase = any(
                len(names[name]) == 1 and f" {name} " in f" {filtered} " for name in labels[node.id]
            )
            if wanted & alias_words and not unique_phrase:
                continue
        score, coverage = _lexical(node, wanted)
        if score:
            scored.append((score, coverage, node.id))
    return [ref for _, _, ref in sorted(scored, key=lambda row: (-row[0], -row[1], row[2]))][:8], []


def _edge_order(edge: Edge) -> tuple:
    return (
        edge.origin == "lexical",
        edge.relation != "prerequisite_of",
        edge.relation == "contains",
        edge.start,
        edge.end,
        edge.relation,
        edge.assertion or "",
    )


def walk(graph: Graph, selected: list[str], checks: AssertionChecks, *, outgoing: bool = False):
    adjacency: dict[str, list[tuple[Edge, str, str]]] = {}
    for edge in sorted(graph.edges, key=_edge_order):
        if edge.relation in NAVIGATION:
            continue
        adjacency.setdefault(edge.start, []).append((edge, edge.end, "forward"))
        if not outgoing:
            adjacency.setdefault(edge.end, []).append((edge, edge.start, "reverse"))
    routes = {ref: ([], [ref]) for ref in selected}
    pending = deque((ref, False) for ref in selected)
    examined = 0
    exhausted = False
    while pending:
        current, terminal = pending.popleft()
        path, refs = routes[current]
        if len(path) >= 2 or terminal:
            continue
        for edge, target, direction in adjacency.get(current, []):
            examined += 1
            if examined > 2048:
                return routes, True
            if target in routes or not checks.edge(edge):
                continue
            if len(routes) >= 256:
                exhausted = True
                continue
            # Containment may identify a parent, never connect its unrelated children.
            is_terminal = edge.relation == "contains" and direction == "reverse"
            routes[target] = (path + [(edge, direction)], refs + [target])
            pending.append((target, is_terminal))
    return routes, exhausted


def _path(
    graph: Graph, target: str, route, views: dict[str, dict], checks: AssertionChecks
) -> dict:
    edges, refs = route
    steps = []
    for edge, direction in edges:
        step: dict[str, JsonValue] = {
            "from": edge.start,
            "to": edge.end,
            "relation": edge.relation,
            "origin": edge.origin,
            "traversal": direction,
            "conditions": [excerpt(c) for c in edge.conditions],
        }
        if edge.assertion:
            assertion = graph.assertions[edge.assertion]
            assessment = checks.assertion(edge.assertion)
            step["assertion"] = assertion.key
            step["rationale"] = excerpt(assertion.rationale)
            step["support_groups"] = [
                {
                    "key": group.key,
                    "current": status.current,
                    "evidence": [e.model_dump(mode="json") for e in group.evidence],
                }
                for group, status in zip(assertion.support_groups, assessment.groups, strict=True)
            ]
        steps.append(step)
    return {
        "target": target,
        "nodes": refs,
        "steps": steps,
        "usable_as_evidence": all(
            views[ref]["usable_as_evidence"] or graph.nodes[ref].workspace == "concept"
            for ref in refs
        ),
    }


def _collect(
    graph: Graph,
    selected: list[str],
    selector: dict,
    purpose: Purpose,
    limit: int,
    max_bytes: int,
    *,
    outgoing: bool = False,
) -> dict:
    evidence = EvidenceChecks(graph.inputs)
    checks = AssertionChecks(graph, evidence)
    packet = envelope(graph, selector)
    routes, exhausted = walk(graph, selected, checks, outgoing=outgoing)
    refs = [ref for ref in routes if graph.nodes[ref].workspace in LEARNING]
    refs.sort(
        key=lambda ref: (
            graph.nodes[ref].workspace != purpose,
            graph.nodes[ref].scope.get("role") == "enrichment",
            ref not in selected,
            not any(edge.origin == "reviewed" for edge, _ in routes[ref][0]),
            len(routes[ref][0]),
            ref,
        )
    )
    views: dict[str, dict] = {}

    def current(ref: str) -> bool:
        if ref not in views:
            views[ref] = item_view(graph.nodes[ref], evidence)
        return views[ref]["evidence_status"] == "current"

    # Find a current home per workspace before filling remaining slots. Unchecked
    # candidates cannot displace an already selected current item in this order.
    primary: list[str] = []
    spaces = dict.fromkeys(graph.nodes[ref].workspace for ref in refs)
    for space in spaces:
        home = next(
            (ref for ref in refs if graph.nodes[ref].workspace == space and current(ref)), None
        )
        if home is not None:
            primary.append(home)
    primary.sort(key=refs.index)
    chosen = primary[:limit]
    for ref in refs:
        if len(chosen) >= limit:
            break
        if ref not in primary and current(ref):
            chosen.append(ref)
    if len(chosen) < limit:
        # The scan exhausted every candidate: all remaining views are noncurrent.
        chosen += [ref for ref in refs if ref not in chosen][: limit - len(chosen)]
    needed = {ref for target in chosen for ref in routes[target][1]}
    for ref in sorted(needed - views.keys()):
        views[ref] = item_view(graph.nodes[ref], evidence)
    packet["items"] = [views[ref] for ref in chosen]
    packet["paths"] = [_path(graph, ref, routes[ref], views, checks) for ref in chosen]
    packet["nodes"] = [views[ref] for ref in sorted(needed) if ref not in chosen]
    packet["issues"] = [
        {"code": issue.code, "ref": issue.ref, "message": issue.message}
        for issue in graph.issues[:30]
    ]
    packet["omitted"] = {"item_limit": len(refs) - len(chosen)} if len(refs) > limit else {}
    if len(graph.issues) > 30:
        packet["omitted"]["issues"] = len(graph.issues) - 30
    packet["truncation"].update(traversal=exhausted, verification=evidence.exhausted)
    packet["status"] = (
        "partial"
        if exhausted or evidence.exhausted or len(graph.issues) > 30
        else "ok"
        if chosen
        else "empty"
    )
    packet["scope"]["checked"] = sorted(evidence.payloads)
    packet["scope"]["checked_lectures"] = sorted(evidence.lectures)
    packet["snapshot_digest"] = graph.inputs.reader.verify()
    return fit(packet, max_bytes)


def _limits(limit: int, max_bytes: int) -> None:
    if not 1 <= limit <= 30 or not 2048 <= max_bytes <= 65536:
        raise CampusError(Code.INVALID_RESPONSE, "Use limit 1–30 and max-bytes 2048–65536.")


def context(
    project_path: Path,
    query: str | None = None,
    *,
    item: str | None = None,
    concept: str | None = None,
    purpose: Purpose = "study",
    limit: int = 12,
    max_bytes: int = 24000,
) -> dict:
    _limits(limit, max_bytes)
    if purpose not in {"study", "lectures", "exercises", "exam", "review"}:
        raise CampusError(Code.INVALID_RESPONSE, "Unknown context purpose.")
    if sum(value is not None for value in (query, item, concept)) != 1 or (
        query is not None and (not query.strip() or len(query) > 500)
    ):
        raise CampusError(
            Code.INVALID_RESPONSE,
            "Choose exactly one nonempty query (up to 500 characters), item or concept.",
        )
    graph = project(load_inputs(project_path))
    selector = (
        {"query": excerpt(query, 2000)}
        if query is not None
        else {"item": item}
        if item is not None
        else {"concept": concept}
    )
    selector["purpose"] = purpose
    if query is not None:
        selected, ambiguous = seeds(graph, query)
    else:
        selected, ambiguous = [item if item is not None else f"concept/{concept}"], []
        if selected[0] not in graph.nodes or graph.nodes[selected[0]].workspace not in LEARNING | {
            "concept"
        }:
            raise CampusError(
                Code.INVALID_RESPONSE, "Unknown exact item or concept in this course."
            )
    if ambiguous:
        packet = envelope(graph, selector)
        packet.update(
            status="ambiguous",
            candidates=[
                {"id": ref, "label": excerpt(graph.nodes[ref].title, 200)} for ref in ambiguous
            ],
        )
        packet["snapshot_digest"] = graph.inputs.reader.verify()
        return fit(packet, max_bytes)
    return _collect(graph, selected, selector, purpose, limit, max_bytes)


def impact(project_path: Path, source: str, *, limit: int = 12, max_bytes: int = 24000) -> dict:
    _limits(limit, max_bytes)
    graph = project(load_inputs(project_path))
    ref = f"source/{source}"
    if ref not in graph.nodes:
        packet = envelope(graph, {"source": excerpt(source, 200)})
        packet.update(unknown_source=True, unmapped=False, direct=[], review_candidates=[])
        packet["snapshot_digest"] = graph.inputs.reader.verify()
        return fit(packet, max_bytes)
    direct = sorted(
        {edge.start for edge in graph.edges if edge.end == ref and edge.relation == "supported_by"}
    )
    packet = _collect(
        graph, direct[:8], {"source": source}, "review", limit, max_bytes, outgoing=True
    )
    packet["direct"] = [row["id"] for row in packet["items"] if row["id"] in direct]
    packet["review_candidates"] = [row["id"] for row in packet["items"] if row["id"] not in direct]
    packet["assertion_candidates"] = [
        key
        for key, a in sorted(graph.assertions.items())
        if any(
            e.kind == "source" and e.source == source for g in a.support_groups for e in g.evidence
        )
    ]
    stored = graph.inputs.resources.get(source)
    packet.update(
        unknown_source=stored is None,
        unmapped=not direct,
        source_status=stored.status if stored else "unknown",
    )
    if len(direct) > 8:
        packet["omitted"]["impact_seeds"] = len(direct) - 8
        packet["status"] = "partial"
    # Assertion diagnostics are bounded as whole keys, including inactive records.
    if len(packet["assertion_candidates"]) > 30:
        packet["omitted"]["assertion_candidates"] = len(packet["assertion_candidates"]) - 30
        packet["assertion_candidates"] = packet["assertion_candidates"][:30]
        packet["status"] = "partial"
    return fit(packet, max_bytes)
