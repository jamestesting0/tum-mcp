"""Safe bounded views of private graph data. Native content never leaves wholesale."""

import json
import re

from pydantic import JsonValue

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_knowledge_evidence import EvidenceChecks, Validity
from tum_mcp.study_knowledge_graph import Graph, Node


def encoded(value: JsonValue) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def excerpt(value: str, limit: int = 400) -> str:
    # URLs are not a locator API; callers get typed local follow-up arguments.
    value = re.sub(r"(?:https?://|file://)\S+", "[link omitted]", value, flags=re.IGNORECASE)
    return value.encode()[:limit].decode("utf-8", errors="ignore")


def validity(node: Node, evidence: EvidenceChecks) -> Validity:
    states = [evidence.source(source) for source in node.sources]
    if node.workspace == "lectures" and isinstance(node.scope.get("lecture"), str):
        keys = tuple(node.payload.get("evidence", [])) if node.kind == "section" else None
        states.extend(evidence.selection(node.scope["lecture"], keys))
    for state in ("stale", "unverified", "unknown"):
        if any(item.state == state for item in states):
            return next(item for item in states if item.state == state)
    return (
        Validity("current") if states else Validity("unknown", "navigation without source evidence")
    )


def item_view(node: Node, evidence: EvidenceChecks) -> dict[str, JsonValue]:
    state = validity(node, evidence)
    locators: list[JsonValue] = []
    for source in dict.fromkeys(node.sources):
        locator: dict[str, JsonValue] = {
            "kind": "source",
            "source": source.key,
            "sha256": source.sha256,
            "evidence_status": evidence.source(source).state,
            "follow_up": ["study", "text", ".", "--key", source.key],
        }
        if isinstance(node.payload, dict) and isinstance(node.payload.get("pages"), str):
            locator["pages"] = node.payload["pages"]
            locator["follow_up"] += ["--pages", node.payload["pages"]]
        locators.append(locator)
    if node.workspace == "lectures" and evidence.inputs.lectures:
        keys = node.payload.get("evidence", []) if isinstance(node.payload, dict) else []
        for record in evidence.inputs.lectures.evidence:
            if record.key in keys and record.interval is not None:
                locators.append(
                    {
                        "kind": "time",
                        "evidence": record.key,
                        "start_s": record.interval.start_s,
                        "end_s": record.interval.end_s,
                        "reviewed": record.reviewed,
                        "uncertain": bool(record.uncertainty),
                    }
                )
    return {
        "id": node.id,
        "workspace": node.workspace,
        "kind": node.kind,
        "title": excerpt(node.title, 200),
        "excerpt": excerpt(node.summary or node.body),
        "text_role": "quoted_course_data",
        "granularity": node.granularity,
        "evidence_status": state.state,
        "usable_as_evidence": state.current,
        "tags": {
            key: value
            for key, value in node.scope.items()
            if key
            in {
                "role",
                "origin",
                "solution_origin",
                "relevance",
                "classification",
                "question_number",
            }
        },
        "source_roles": [
            {"source": source["key"], "role": source["role"]}
            for source in node.scope.get("source_roles", [])
        ],
        "locators": locators,
    }


def envelope(graph: Graph, selector: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "status": "empty",
        "course": {
            "key": graph.inputs.state.course.key,
            "semester": graph.inputs.state.course.semester,
        },
        "snapshot_digest": "",
        "scope": {
            "present": list(graph.inputs.workspaces),
            "checked": [],
            "inputs": ["state", "study", "exercises", "exam", "lectures", "coverage", "knowledge"],
        },
        "selector": selector,
        "items": [],
        "paths": [],
        "nodes": [],
        "issues": [],
        "omitted": {},
        "truncation": {"output_budget": False, "traversal": False, "verification": False},
    }


def fit(packet: dict[str, JsonValue], max_bytes: int) -> dict[str, JsonValue]:
    """Drop complete lowest-ranked paths/items and their unused navigation nodes."""
    while len(encoded(packet)) > max_bytes:
        packet["truncation"]["output_budget"] = True
        packet["status"] = "partial"
        if packet["items"]:
            removed = packet["items"].pop()["id"]
            for name in ("direct", "review_candidates"):
                if name in packet:
                    packet[name] = [ref for ref in packet[name] if ref != removed]
            packet["paths"] = [path for path in packet["paths"] if path["target"] != removed]
            refs = {node for path in packet["paths"] for node in path["nodes"]}
            packet["nodes"] = [node for node in packet["nodes"] if node["id"] in refs]
            packet["omitted"]["output_budget"] = packet["omitted"].get("output_budget", 0) + 1
        elif packet["issues"]:
            packet["issues"].pop()
            packet["omitted"]["issues"] = packet["omitted"].get("issues", 0) + 1
        elif packet.get("assertion_candidates"):
            packet["assertion_candidates"].pop()
            packet["omitted"]["assertion_candidates"] = (
                packet["omitted"].get("assertion_candidates", 0) + 1
            )
        elif packet.get("candidates"):
            packet["candidates"].pop()
            packet["omitted"]["candidates"] = packet["omitted"].get("candidates", 0) + 1
        else:
            raise CampusError(
                Code.INVALID_RESPONSE, "The complete context envelope exceeds the byte budget."
            )
    return packet
