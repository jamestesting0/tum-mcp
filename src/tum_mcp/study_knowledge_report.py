"""Explicit full local audit. Unlike context, this operation has no retrieval budget."""

from collections import Counter
from pathlib import Path

from tum_mcp.extension_selection import course_memory_enabled
from tum_mcp.study_knowledge_assertions import AssertionChecks
from tum_mcp.study_knowledge_evidence import EvidenceChecks
from tum_mcp.study_knowledge_packet import excerpt
from tum_mcp.study_knowledge_projection import project
from tum_mcp.study_knowledge_store import load_inputs


def knowledge_report(root: Path) -> dict:
    graph = project(load_inputs(root))
    checks = AssertionChecks(graph, EvidenceChecks(graph.inputs, full=True))
    rows = []
    for key, assertion in sorted(graph.assertions.items()):
        status = checks.assertion(key)
        rows.append(
            {
                "key": key,
                "declared_status": assertion.review.status,
                "state": status.state,
                "expected_revision": status.expected_revision,
                "ready_for_review": status.ready_for_review,
                "problems": list(status.problems),
                "from": assertion.start.node_id,
                "to": assertion.end.node_id,
                "relation": assertion.relation,
                "support_groups": [
                    {
                        "key": group.key,
                        "current": group.current,
                        "evidence": [
                            {"state": e.state, "reason": e.reason} for e in group.evidence
                        ],
                    }
                    for group in status.groups
                ],
            }
        )
    semantic_revision = checks.semantic_revision()
    return {
        "schema_version": 1,
        "audit_scope": "full_local_semantic_audit",
        "course": {
            "key": graph.inputs.state.course.key,
            "semester": graph.inputs.state.course.semester,
        },
        "workspaces": list(graph.inputs.workspaces),
        "knowledge_revision": semantic_revision,
        "counts": {
            "nodes": len(graph.nodes),
            "native_edges": sum(e.origin == "native" for e in graph.edges),
            "assertions": dict(Counter(row["state"] for row in rows)),
        },
        "assertions": rows,
        "issues": [
            {"code": issue.code, "ref": issue.ref, "message": excerpt(issue.message)}
            for issue in graph.issues
        ],
        "snapshot_digest": graph.inputs.reader.verify(),
    }


def knowledge_revision(root: Path) -> str | None:
    if not course_memory_enabled():
        return None
    from tum_mcp.study_store import private_path

    if not private_path(root, "knowledge.json").exists():
        return None
    return knowledge_report(root)["knowledge_revision"]
