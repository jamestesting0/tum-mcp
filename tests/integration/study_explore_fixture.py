"""Source-backed Explore setup shared by build, export and real-browser regressions."""

import json
from pathlib import Path

from tum_mcp.study_models import Resource, ResourceState
from tum_mcp.study_store import digest, load_state, private_path


def add_explore(project: Path) -> None:
    """Give BFS optional material from a distinct synthetic source, with a classification."""
    state = load_state(project)
    body = b"Synthetic supporting material: the origins of a queue-based search.\n"
    relative = "materials/content/material-explore-source.md"
    (project / relative).write_bytes(body)
    source = Resource(
        key="explore-source",
        binding=state.course.bindings[0].key,
        kind="content",
        title="Context and origins",
        url="https://example.invalid/explore",
        locator="Synthetic note",
    )
    stored = ResourceState(resource=source, path=relative, sha256=digest(body), status="current")
    private_path(project, "state.json").write_text(
        state.model_copy(update={"resources": (*state.resources, stored)}).model_dump_json(),
        encoding="utf-8",
    )
    path = project / "study/content.json"
    payload = json.loads(path.read_bytes())
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    unit["explore"] = [
        {
            "key": "origin",
            "title": "Where the idea came from",
            "sources": [{"key": source.key, "sha256": digest(body)}],
            "blocks": [
                {
                    "key": "history",
                    "kind": "text",
                    "title": "Historical context",
                    "sources": [source.key],
                    "paragraphs": ["A synthetic supporting passage."],
                }
            ],
        }
    ]
    path.write_text(json.dumps(payload))
    private_path(project, "coverage.json").write_text(
        json.dumps(
            {
                "course_key": state.course.key,
                "sources": [
                    {
                        "source": source.key,
                        "status": {"checked_at": "2026-10-30"},
                        "outcomes": [
                            {
                                "key": "origins",
                                "text": "Describe the historical background.",
                                "locator": "Synthetic note",
                                "status": "covered",
                                "role": "enrichment",
                                "classification": {
                                    "basis": "reviewed_enrichment",
                                    "reason": (
                                        "Core tasks do not depend on this synthetic background."
                                    ),
                                },
                                "explore": [{"unit": "bfs", "item": "origin"}],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
