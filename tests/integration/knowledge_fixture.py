"""Synthetic course evidence shared by knowledge and replay integration scenarios."""

import json
from pathlib import Path

from documents import content_file
from material_fixture import (
    EXAM_FILES,
    exam_document,
    minimal_unit,
    pdf_bytes,
    text,
    with_guided_paper,
)

from tum_mcp.course.project.store import load_state
from tum_mcp.course.project.sync import sync

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
        content_file(root, "study").write_text(
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
                    "schema_version": 2,
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
                                    "units": ["observer"],
                                },
                                {
                                    "key": "observer-extension",
                                    "text": "Compare optional notification scheduling.",
                                    "locator": "Page 1",
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
        content_file(root, "exercises").write_text(
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
        content_file(root, "exam").write_text(json.dumps(exam_document(root)), encoding="utf-8")
    if "lectures" in workspaces:
        payload = json.loads(
            (Path(__file__).parents[1] / "fixtures/course_app/lectures.json").read_bytes()
        )
        payload["course_key"] = course
        lecture = payload["lectures"][0]
        lecture.update(
            key="observer-lecture",
            title="Observer clarification",
            summary="Registration separates the subject from display implementations.",
            sources=[{"key": "slides", "sha256": source.sha256}],
            notes=[
                {
                    "key": "registration",
                    "title": "Who calls the observers",
                    "context": "The slide shows displays updating when the subject changes.",
                    "text": "The subject invokes registered observer interfaces.",
                    "sources": ["slides"],
                    "evidence": [payload["evidence"][0]["key"]],
                }
            ],
            highlights=[],
        )
        payload["evidence"] = payload["evidence"][:1]
        for evidence in payload["evidence"]:
            evidence.update(source_key="slides", source_sha256=source.sha256)
        content_file(root, "lectures").write_text(json.dumps(payload), encoding="utf-8")
    if layout[1] != ".tum-mcp":
        (root / ".tum-mcp").rename(root / layout[1])
    return root


PASSAGE = {"unit": "observer", "block": "observer-definition"}


def fidelity_project(tmp_path: Path) -> Path:
    """The knowledge course plus one instance of every authored link family and entries that
    cite a subset of their owner's sources."""
    from tum_mcp.course.checks.links import record_none
    from tum_mcp.course.memory.store import load_inputs

    root = knowledge_project(tmp_path)
    sha = {item.resource.key: item.sha256 for item in load_state(root).resources}

    def version(key: str) -> dict:
        return {"key": key, "sha256": sha[key]}

    def edit(workspace: str, change) -> None:
        path = content_file(root, workspace)
        value = json.loads(path.read_bytes())
        change(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def study(value: dict) -> None:
        unit = value["units"][0]
        unit["sources"].append(version("exam-ws23"))
        unit["blocks"].append(
            text("Exam use", "exam-ws23", "The weather station task applies Observer.")
            | {"key": "exam-link", "pages": "1"}
        )

    def exercises(value: dict) -> None:
        practice = value["sets"][0]["exercises"][0]
        practice["sources"].append(version("exam-ws23"))
        value["sets"][0]["exercises"].append(
            {
                "key": "observer-drill",
                "label": "Drill 1",
                "title": "Register a display",
                "kind": "distilled",
                "distilled_from": ["observer-practice"],
                "sources": [version("slides")],
                "statement": [
                    text("Task", "slides", "Register one more display."),
                    {
                        "kind": "table",
                        "title": "Calls",
                        "sources": ["slides"],
                        "caption": "Subject calls",
                        "columns": ["Call", "Effect"],
                        "rows": [["attach", "registers a display"]],
                    },
                ],
                "objectives": ["Register a display with the subject."],
                "steps": [
                    {
                        "key": "register",
                        "purpose": "Find the call.",
                        "prompt": "Which call registers the display?",
                        "explanation": "The subject's attach call.",
                    }
                ],
                "solution": {"answers": [{"blocks": [text("Answer", "slides", "Call attach.")]}]},
            }
        )

    def exam(value: dict) -> None:
        with_guided_paper(value)
        concept = next(item for item in value["concepts"] if item["key"] == "observer")
        concept.update(
            units=["observer"],
            passages=[PASSAGE],
            exercises=[{"set": "sheet-1", "exercise": "observer-practice"}],
        )
        value["topics"][0]["units"] = ["observer"]
        question = value["sittings"][0]["variants"][0]["questions"][0]
        question["guidance"]["prerequisites"] = [
            PASSAGE | {"explanation": "Use the notification contract."}
        ]

    def lectures(value: dict) -> None:
        lecture = value["lectures"][0]
        lecture["sources"].append(version("exam-ws22-upload"))
        lecture["notes"][0]["passage"] = PASSAGE

    for workspace, change in (
        ("study", study),
        ("exercises", exercises),
        ("exam", exam),
        ("lectures", lectures),
    ):
        edit(workspace, change)
    inputs = load_inputs(root)
    record_none(
        root,
        inputs.study,
        inputs.exercises,
        inputs.exam,
        inputs.lectures,
        "concept:decorator",
        "exercises",
        "No sheet exercise trains Decorator yet.",
    )
    return root
