"""Resolve annotation review fingerprints and source-backed activation lazily."""

from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import JsonValue

from tum_mcp.study_knowledge_evidence import EvidenceChecks, GroupStatus
from tum_mcp.study_knowledge_graph import Edge, Graph, Node
from tum_mcp.study_knowledge_models import Assertion, LectureEvidence, canonical_digest

AssertionState = Literal[
    "candidate", "rejected", "current", "stale", "unsupported", "invalid", "unverified"
]


@dataclass(frozen=True, slots=True)
class Assessment:
    key: str
    state: AssertionState
    expected_revision: str | None
    groups: tuple[GroupStatus, ...] = ()
    problems: tuple[str, ...] = ()
    ready_for_review: bool = False


def review_revision(graph: Graph, assertion: Assertion) -> str | None:
    endpoints = [graph.nodes.get(endpoint.node_id) for endpoint in (assertion.start, assertion.end)]
    if any(node is None for node in endpoints):
        return None
    evidence_records: list[JsonValue] = []
    selected = {
        (e.lecture, e.evidence)
        for group in assertion.support_groups
        for e in group.evidence
        if isinstance(e, LectureEvidence)
    }
    if content := graph.inputs.lectures:
        for node in endpoints:
            if node is not None and node.workspace == "lectures":
                key = node.scope.get("lecture")
                for lecture in content.lectures:
                    if lecture.key == key:
                        for section in lecture.sections:
                            if node.kind == "lecture" or node.id.endswith(
                                f"/section/{section.key}"
                            ):
                                selected.update((lecture.key, key) for key in section.evidence)
        for lecture_key, evidence_key in sorted(selected):
            record = next((e for e in content.evidence if e.key == evidence_key), None)
            lecture = next((item for item in content.lectures if item.key == lecture_key), None)
            if (
                record is None
                or lecture is None
                or not any(record.key in s.evidence for s in lecture.sections)
            ):
                return None
            evidence_records.append(record.model_dump(mode="json"))
    elif selected:
        return None
    body = assertion.model_dump(mode="json", by_alias=True, exclude={"review"})
    body["support_groups"] = [
        {
            "key": group.key,
            "evidence": sorted(
                (e.model_dump(mode="json") for e in group.evidence), key=canonical_digest
            ),
        }
        for group in sorted(assertion.support_groups, key=lambda group: group.key)
    ]
    payload: JsonValue = {
        "course": {
            "key": graph.inputs.state.course.key,
            "semester": graph.inputs.state.course.semester,
        },
        "assertion": body,
        "endpoints": {
            node.id: {
                "item": node.payload,
                "sources": [s.model_dump(mode="json") for s in node.sources],
                "scope": node.scope,
            }
            for node in endpoints
            if node is not None
        },
        "lecture_evidence": evidence_records,
    }
    return canonical_digest(payload)


def _role(assertion: Assertion, node: Node) -> bool:
    match assertion.relation:
        case "prerequisite_of" | "contrasts":
            return node.workspace == "concept"
        case "practices":
            return node.kind in {"question", "flashcard", "exercise", "step"}
        case "assesses":
            return node.kind == "mock_question" or (
                node.kind == "past_question" and node.scope.get("classification") == "classified"
            )
        case "teaches":
            return (node.workspace == "study" and node.kind in {"unit", "block", "explore"}) or (
                node.workspace == "exam" and node.kind in {"concept", "pattern"}
            )
        case "clarifies":
            return (
                (node.workspace == "lectures" and node.kind in {"lecture", "section"})
                or (node.workspace == "study" and node.kind in {"unit", "block", "explore"})
                or (node.workspace == "exam" and node.kind in {"concept", "pattern"})
            )


def cycle_groups(edges: set[Edge]) -> dict[str, frozenset[str]]:
    selected = [e for e in edges if e.origin == "reviewed" and e.relation == "prerequisite_of"]
    forward: dict[str, list[str]] = {}
    backward: dict[str, list[str]] = {}
    for edge in selected:
        forward.setdefault(edge.start, []).append(edge.end)
        forward.setdefault(edge.end, [])
        backward.setdefault(edge.end, []).append(edge.start)
        backward.setdefault(edge.start, [])
    seen: set[str] = set()
    order: list[str] = []
    for node in forward:
        stack = [(node, False)]
        while stack:
            current, finished = stack.pop()
            if finished:
                order.append(current)
            elif current not in seen:
                seen.add(current)
                stack.append((current, True))
                stack.extend((child, False) for child in forward[current] if child not in seen)
    assigned: set[str] = set()
    groups: dict[str, frozenset[str]] = {}
    for node in reversed(order):
        if node in assigned:
            continue
        component: set[str] = set()
        pending = [node]
        while pending:
            current = pending.pop()
            if current not in assigned:
                assigned.add(current)
                component.add(current)
                pending.extend(backward[current])
        if len(component) > 1:
            keys = frozenset(
                e.assertion
                for e in selected
                if e.start in component and e.end in component and e.assertion is not None
            )
            groups.update((key, keys) for key in keys)
    return groups


@dataclass(slots=True)
class AssertionChecks:
    """Request-local memo; source I/O happens only for inspected assertions/components."""

    graph: Graph
    evidence: EvidenceChecks
    assessments: dict[str, Assessment] = field(default_factory=dict)
    components: dict[str, frozenset[str]] = field(init=False)
    checked_components: set[frozenset[str]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.components = cycle_groups(self.graph.edges)

    def _basic(self, key: str) -> Assessment:
        if key in self.assessments:
            return self.assessments[key]
        assertion = self.graph.assertions[key]
        revision = review_revision(self.graph, assertion)
        node = self.graph.nodes.get(assertion.start.node_id)
        problems = []
        if revision is None:
            problems.append("missing_endpoint_or_timed_evidence")
        if node is not None and not _role(assertion, node):
            problems.append("invalid_item_role")
        groups = tuple(self.evidence.group(group) for group in assertion.support_groups)
        for endpoint in (assertion.start, assertion.end):
            item = self.graph.nodes.get(endpoint.node_id)
            if item is None:
                continue
            states = [self.evidence.source(source) for source in item.sources]
            if item.workspace == "lectures" and isinstance(item.scope.get("lecture"), str):
                keys = tuple(item.payload.get("evidence", [])) if item.kind == "section" else None
                states.extend(self.evidence.selection(item.scope["lecture"], keys))
            if any(not state.current for state in states):
                problems.append("endpoint_evidence_not_current")
        supported = any(group.current for group in groups)
        ready = revision is not None and not problems and supported
        if assertion.review.status in {"candidate", "rejected"}:
            state = assertion.review.status
        elif problems:
            state = "invalid"
        elif assertion.review.revision != revision:
            state = "stale"
        elif not supported:
            state = "unverified" if self.evidence.exhausted else "unsupported"
        else:
            state = "current"
        result = Assessment(key, state, revision, groups, tuple(problems), ready)
        self.assessments[key] = result
        if ready and state == "candidate" and assertion.relation == "prerequisite_of":
            prospective = {
                edge
                for edge in self.graph.edges
                if edge.origin == "reviewed"
                and edge.relation == "prerequisite_of"
                and edge.assertion is not None
                and self._basic(edge.assertion).state == "current"
            }
            prospective.add(
                Edge(
                    assertion.start.node_id,
                    assertion.end.node_id,
                    "prerequisite_of",
                    "reviewed",
                    key,
                )
            )
            if key in cycle_groups(prospective):
                result = replace(
                    result, problems=("would_create_prerequisite_cycle",), ready_for_review=False
                )
                self.assessments[key] = result
        return result

    def assertion(self, key: str) -> Assessment:
        component = self.components.get(key)
        if component is not None and component not in self.checked_components:
            self.checked_components.add(component)
            current = {k for k in component if self._basic(k).state == "current"}
            active_edges = {e for e in self.graph.edges if e.assertion in current}
            for cyclic in cycle_groups(active_edges):
                self.assessments[cyclic] = replace(
                    self.assessments[cyclic],
                    state="invalid",
                    problems=("prerequisite_cycle",),
                    ready_for_review=False,
                )
        return self._basic(key)

    def edge(self, edge: Edge) -> bool:
        return edge.assertion is None or self.assertion(edge.assertion).state == "current"

    def semantic_revision(self) -> str | None:
        rows: list[JsonValue] = []
        for key, assertion in sorted(self.graph.assertions.items()):
            if assertion.review.status != "reviewed":
                continue
            assessment = self.assertion(key)
            rows.append(
                {
                    "assertion": assertion.model_dump(mode="json"),
                    "expected_revision": assessment.expected_revision,
                    "state": assessment.state,
                    "groups": [
                        {
                            "key": g.key,
                            "current": g.current,
                            "evidence": [
                                {"state": v.state, "reason": v.reason} for v in g.evidence
                            ],
                        }
                        for g in assessment.groups
                    ],
                    "problems": list(assessment.problems),
                }
            )
        return canonical_digest(rows) if rows else None
