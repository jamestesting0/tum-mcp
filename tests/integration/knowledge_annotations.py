"""Explicit synthetic review decisions; production reads never approve annotations."""

import json
from pathlib import Path

from tum_mcp.study_knowledge_assertions import review_revision
from tum_mcp.study_knowledge_projection import project
from tum_mcp.study_knowledge_store import load_inputs
from tum_mcp.study_store import load_state, private_path


def annotation(root: Path, ref: str = "study/unit/observer", key: str = "teaching") -> dict:
    source = next(s for s in load_state(root).resources if s.resource.key == "slides")
    return {
        "key": key,
        "relation": "teaches",
        "from": {"kind": "item", "ref": ref},
        "to": {"kind": "concept", "key": "observer"},
        "rationale": "The synthetic passage explains Observer.",
        "conditions": ["Observers register before notification."],
        "support_groups": [
            {
                "key": "slides",
                "evidence": [
                    {"kind": "source", "source": "slides", "sha256": source.sha256, "pages": "1"}
                ],
            }
        ],
        "review": {"status": "candidate", "revision": None},
    }


def write_registry(root: Path, assertions: list[dict], *, reviewed: bool = False) -> None:
    state = load_state(root)
    value = {
        "schema_version": 1,
        "course_key": state.course.key,
        "semester": state.course.semester,
        "concepts": [
            {"key": "observer", "label": "Observer", "aliases": ["Notification pattern"]},
            {"key": "coupling", "label": "Loose coupling", "aliases": ["Notification pattern"]},
        ],
        "assertions": assertions,
    }
    path = private_path(root, "knowledge.json")
    path.write_text(json.dumps(value), encoding="utf-8")
    if reviewed:
        graph = project(load_inputs(root))
        for row in value["assertions"]:
            revision = review_revision(graph, graph.assertions[row["key"]])
            assert revision is not None
            row["review"] = {"status": "reviewed", "revision": revision}
        path.write_text(json.dumps(value), encoding="utf-8")


def connected_annotations(root: Path) -> list[dict]:
    return [
        annotation(root),
        annotation(root, "exercises/set/sheet-1/exercise/observer-practice", "practice")
        | {"relation": "practices"},
        annotation(root, "exam/concept/observer", "exam-teaching"),
        annotation(root, "lectures/lecture/observer-lecture/section/registration", "lecture")
        | {"relation": "clarifies"},
    ]
