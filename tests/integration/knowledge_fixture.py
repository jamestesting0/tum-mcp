"""Synthetic course evidence shared by knowledge and replay integration scenarios."""

import json
from pathlib import Path

from material_fixture import EXAM_FILES, exam_document, minimal_unit, pdf_bytes, text

from tum_mcp.study_store import load_state
from tum_mcp.study_sync import sync

WORKSPACES = frozenset({"study", "exercises", "exam", "lectures"})


def knowledge_project(
    tmp_path: Path,
    layout: tuple[str, str] = ("app", ".tum-mcp"),
    workspaces: frozenset[str] = WORKSPACES,
) -> Path:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    resources = []
    for key, (kind, pages) in EXAM_FILES.items():
        filename = f"{key}.pdf"
        (incoming / filename).write_bytes(pdf_bytes(pages))
        resources.append(
            {
                "key": key,
                "binding": "sample",
                "kind": kind,
                "title": key.replace("-", " "),
                "url": f"https://example.invalid/{key}",
                "revision": "1",
                "source_file": filename,
            }
        )
    snapshot = incoming / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "course": {
                    "key": "synthetic-pse-ws26",
                    "title": "Synthetic Patterns",
                    "semester": "WS26/27",
                    "synthetic": True,
                    "bindings": [{"key": "sample", "provider": "sample", "course_id": "42"}],
                },
                "coverage": [
                    {"binding": "sample", "status": "complete", "checked_at": "2026-10-31"}
                ],
                "resources": resources,
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "course"
    sync(root, snapshot, course_input="Synthetic Patterns")
    state = load_state(root)
    source = next(item for item in state.resources if item.resource.key == "slides")
    course = state.course.key
    app = root / "app"
    app.mkdir()
    if "study" in workspaces:
        units = [minimal_unit(key, "slides", source.sha256) for key in ("observer", "strategy")]
        units[0]["summary"] = "Observer decouples subjects from observers."
        units[0]["blocks"][0] = {
            "kind": "definition",
            "key": "observer-definition",
            "title": "Observer",
            "sources": ["slides"],
            "pages": "1",
            "term": "Observer",
            "statement": "A subject notifies registered observers when its state changes.",
            "conditions": ["Observers register before notification."],
        }
        units[0]["lectures"] = ["observer-lecture"] if "lectures" in workspaces else []
        units[0]["explore"] = [
            {
                "key": "observer-extra",
                "title": "Optional Observer variants",
                "sources": [{"key": "slides", "sha256": source.sha256}],
                "blocks": [
                    text("Optional extension", "slides", "Compare notification scheduling choices.")
                    | {"key": "observer-enrichment"}
                ],
            }
        ]
        (app / "content.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "course_key": course,
                    "organization": "topics",
                    "introduction": "Synthetic teaching, practice and assessment evidence.",
                    "units": units,
                }
            ),
            encoding="utf-8",
        )
        (root / ".tum-mcp/coverage.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "course_key": course,
                    "sources": [
                        {
                            "source": "slides",
                            "status": {
                                "availability": "released",
                                "taught": "yes",
                                "checked_at": "2026-10-31",
                            },
                            "outcomes": [
                                {
                                    "key": "observer-core",
                                    "text": "Explain Observer registration.",
                                    "locator": "Page 1",
                                    "status": "covered",
                                    "units": ["observer"],
                                },
                                {
                                    "key": "observer-extension",
                                    "text": "Compare optional notification scheduling.",
                                    "locator": "Page 1",
                                    "status": "covered",
                                    "role": "enrichment",
                                    "classification": {
                                        "basis": "reviewed_enrichment",
                                        "reason": "Outside the core objective.",
                                    },
                                    "explore": [{"unit": "observer", "item": "observer-extra"}],
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
    if "exercises" in workspaces:
        exercise = {
            "key": "observer-practice",
            "label": "Problem 1",
            "title": "Add an Observer display",
            "sources": [{"key": "slides", "sha256": source.sha256}],
            "statement": [text("Task", "slides", "Add a display without changing the subject.")],
            "objectives": ["Explain how Observer registration decouples displays."],
            "prerequisites": [
                {
                    "unit": "observer",
                    "block": "observer-definition",
                    "explanation": "Use the notification contract.",
                }
            ]
            if "study" in workspaces
            else [],
            "steps": [
                {
                    "key": "registration",
                    "purpose": "Trace the dependency.",
                    "prompt": "Who stores observers?",
                    "sources": ["slides"],
                    "hints": ["Follow the registration call."],
                    "explanation": "The subject stores observer interfaces.",
                }
            ],
            "solution": {
                "origin": "authored",
                "answers": [
                    {
                        "blocks": [
                            text(
                                "Answer",
                                "slides",
                                "SOLUTION_SECRET: register the new display as an observer.",
                            )
                        ]
                    }
                ],
            },
        }
        (app / "exercises.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "course_key": course,
                    "sets": [{"key": "sheet-1", "title": "Sheet 1", "exercises": [exercise]}],
                }
            ),
            encoding="utf-8",
        )
    if "exam" in workspaces:
        (app / "exam.json").write_text(json.dumps(exam_document(root)), encoding="utf-8")
    if "lectures" in workspaces:
        payload = json.loads(
            (Path(__file__).parents[1] / "fixtures/course_app/lectures.json").read_bytes()
        )
        payload["course_key"] = course
        lecture = payload["lectures"][0]
        lecture.update(
            key="observer-lecture",
            title="Observer clarification",
            overview="Registration separates the subject from display implementations.",
            takeaways=["Notify registered interfaces."],
            sources=[{"key": "slides", "sha256": source.sha256}],
        )
        section = lecture["sections"][0]
        section.update(
            key="registration",
            title="The notification contract",
            blocks=[
                text(
                    "Registration", "slides", "The subject invokes registered observer interfaces."
                )
            ],
            figures=[],
        )
        for evidence in payload["evidence"]:
            evidence.update(source_key="slides", source_sha256=source.sha256)
        (app / "lectures.json").write_text(json.dumps(payload), encoding="utf-8")
    if layout[0] != "app":
        app.rename(root / layout[0])
    if layout[1] != ".tum-mcp":
        (root / ".tum-mcp").rename(root / layout[1])
    return root
