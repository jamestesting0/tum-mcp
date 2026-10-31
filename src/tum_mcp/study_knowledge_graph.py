"""In-memory course items and typed-origin edges; no persistent graph state."""

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from pydantic import JsonValue

from tum_mcp.study_content import SourceVersion
from tum_mcp.study_knowledge_models import Assertion
from tum_mcp.study_knowledge_store import CourseInputs


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    workspace: str
    kind: str
    title: str
    summary: str
    body: str
    payload: JsonValue
    sources: tuple[SourceVersion, ...] = ()
    scope: dict[str, JsonValue] = field(default_factory=dict)
    granularity: Literal["owner", "item"] = "item"


@dataclass(frozen=True, slots=True)
class Edge:
    start: str
    end: str
    relation: str
    origin: Literal["native", "lexical", "reviewed"] = "native"
    assertion: str | None = None
    conditions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    ref: str
    message: str


@dataclass(slots=True)
class Graph:
    """Request-local projection builder; payloads stay private and never enter packets."""

    inputs: CourseInputs
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: set[Edge] = field(default_factory=set)
    assertions: dict[str, Assertion] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    def source(self, key: str) -> str:
        ref = f"source/{key}"
        if ref not in self.nodes:
            stored = self.inputs.resources.get(key)
            self.nodes[ref] = Node(
                ref,
                "source",
                "source",
                stored.resource.title if stored else key,
                "",
                "",
                {"key": key, "status": stored.status if stored else "unknown"},
                granularity="owner",
            )
        return ref

    def add(self, node: Node) -> Node:
        self.nodes[node.id] = node
        for source in node.sources:
            self.edges.add(Edge(node.id, self.source(source.key), "supported_by"))
        return node

    def connect(self, edge: Edge) -> None:
        if edge.start not in self.nodes or edge.end not in self.nodes:
            missing = edge.start if edge.start not in self.nodes else edge.end
            self.issues.append(
                Issue("missing_reference", missing, "A native link needs explicit reconciliation.")
            )
            return
        if (
            edge.relation == "prerequisite_of"
            and self.nodes[edge.start].scope.get("role") == "enrichment"
        ):
            self.issues.append(
                Issue(
                    "enrichment_prerequisite",
                    edge.start,
                    "Optional content cannot satisfy a core prerequisite.",
                )
            )
            return
        self.edges.add(edge)

    def passages(self, owner: Node, blocks: JsonValue) -> None:
        records = list(block_records(blocks))
        counts = Counter(item.get("key") for item in records if item.get("key"))
        for block in records:
            key = block.get("key")
            if not isinstance(key, str):
                continue
            ref = f"{owner.id}/block/{key}"
            if counts[key] != 1:
                self.issues.append(
                    Issue(
                        "ambiguous_block",
                        ref,
                        "Use the stable owner until passage keys are reconciled.",
                    )
                )
                continue
            title = block.get("title") or block.get("term") or key
            self.add(
                Node(
                    ref,
                    owner.workspace,
                    "block",
                    str(title),
                    "",
                    safe_text(block),
                    block,
                    owner.sources,
                    owner.scope,
                )
            )
            self.connect(Edge(owner.id, ref, "contains"))


def block_records(value: JsonValue) -> Iterator[dict[str, JsonValue]]:
    match value:
        case dict():
            if isinstance(value.get("kind"), str) and isinstance(value.get("sources"), list):
                yield value
            for item in value.values():
                yield from block_records(item)
        case list():
            for item in value:
                yield from block_records(item)
        case _:
            return


def safe_text(value: JsonValue) -> str:
    """Index teaching/statement fields, never answers, hints, literals or raw provenance."""
    match value:
        case str():
            return value
        case list():
            return " ".join(safe_text(item) for item in value)
        case dict():
            fields = {
                "title",
                "summary",
                "objectives",
                "text",
                "paragraphs",
                "statement",
                "term",
                "plain",
                "conditions",
                "prompt",
                "front",
                "line",
                "trigger",
                "overview",
                "takeaways",
                "blocks",
                "details",
                "sections",
                "purpose",
                "cues",
            }
            return " ".join(safe_text(item) for key, item in value.items() if key in fields)
        case _:
            return ""
