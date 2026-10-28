"""Small synthetic course projects with real PDF and text materials."""

import json
from pathlib import Path

from tum_mcp.study_sync import sync


def pdf_bytes(pages: list[str]) -> bytes:
    """A valid PDF whose pages carry the given text; an empty string is a page without text."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for text in pages:
        content_id, page_id = len(objects) + 1, len(objects) + 2
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 11 Tf 40 780 Td ({escaped}) Tj ET" if text else ""
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {len(objects) + 2} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        kids.append(f"{page_id} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    body, offsets = b"%PDF-1.4\n", []
    for number, value in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{value}\nendobj\n".encode()
    start = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return body


def material_project(
    tmp_path: Path, files: dict[str, tuple[str, bytes]], *, binding: str = "moodle"
) -> Path:
    """Initialize a project whose resources are files: key -> (kind, bytes)."""
    staging = tmp_path / "incoming"
    staging.mkdir()
    resources = []
    for key, (kind, data) in files.items():
        name = f"{key}.pdf" if data.startswith(b"%PDF-") else f"{key}.md"
        (staging / name).write_bytes(data)
        resources.append(
            {
                "key": key,
                "binding": binding,
                "kind": kind,
                "title": key.replace("-", " ").title(),
                "url": f"https://www.moodle.tum.de/mod/resource/view.php?id={len(resources) + 1}",
                "revision": "1",
                "source_file": name,
            }
        )
    snapshot = staging / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "course": {
                    "key": "synthetic-pse-ws26",
                    "title": "Synthetic Patterns",
                    "semester": "WS26/27",
                    "bindings": [{"key": binding, "provider": "moodle", "course_id": "42"}],
                },
                "coverage": [
                    {"binding": binding, "status": "complete", "checked_at": "2026-10-28T00:00:00Z"}
                ],
                "resources": resources,
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "course"
    sync(root, snapshot, course_input="Synthetic Patterns")
    return root


def minimal_unit(key: str, source: str, sha256: str) -> dict:
    """One schema-valid Study unit citing a single source."""
    return {
        "key": key,
        "label": "Unit",
        "title": key.title(),
        "summary": "Synthetic unit.",
        "minutes": 5,
        "objectives": [{"key": "o1", "text": "Recall the idea."}],
        "sources": [{"key": source, "sha256": sha256}],
        "blocks": [{"kind": "text", "title": "Idea", "sources": [source], "paragraphs": ["Idea."]}],
        "flashcards": [
            {"key": "c1", "objective": "o1", "front": "Idea?", "back": "Idea.", "sources": [source]}
        ],
        "questions": [
            {
                "key": "q1",
                "objective": "o1",
                "prompt": "Which is the idea?",
                "level": "recall",
                "options": [
                    {"key": "a", "text": "Idea", "feedback": "Yes."},
                    {"key": "b", "text": "Other", "feedback": "No."},
                    {"key": "c", "text": "Third", "feedback": "No."},
                ],
                "correct": "a",
                "explanation": "It is the idea.",
                "sources": [source],
            }
        ],
    }


EXAM_FILES = {
    "slides": (
        "content",
        ["Observer decouples subjects from observers", "Strategy swaps algorithms"],
    ),
    "exam-ws23": ("exam", ["Task 1 Observer weather station", "Task 2 Strategy sorting"]),
    "exam-ws23-b": ("exam", ["Task 1 Observer stock ticker", "Task 2 Strategy compression"]),
    "exam-ws23-solution": ("exam", ["Solution Task 1", "Solution Task 2"]),
    "exam-ws22": ("exam", ["Task 1 Observer newsletter", "Task 2 Composite file system"]),
    "exam-ws22-upload": ("exam", ["Task 1 Observer newsletter annotated", "Task 2 Composite"]),
    "exam-ss19": ("exam", ["Task 1 Singleton logger"]),
}


def text(title: str, source: str, *paragraphs: str) -> dict:
    return {"kind": "text", "title": title, "sources": [source], "paragraphs": list(paragraphs)}


def exam_project(tmp_path: Path) -> Path:
    return material_project(
        tmp_path, {key: (kind, pdf_bytes(pages)) for key, (kind, pages) in EXAM_FILES.items()}
    )


def exam_document(root: Path) -> dict:
    """A rich, valid exam.json covering variants, copies, outdated sittings and forecasts."""
    from tum_mcp.study_store import load_state

    state = load_state(root)
    sha = {item.resource.key: item.sha256 for item in state.resources}

    def ref(key: str) -> dict:
        return {"key": key, "sha256": sha[key]}

    def role(key: str, kind: str = "paper") -> dict:
        return {"key": key, "sha256": sha[key], "role": kind}

    def question(
        key: str, number: str, pattern: str, concepts: list[str], source: str, **extra
    ) -> dict:
        value = {
            "key": key,
            "number": number,
            "points": 10,
            "format": "code",
            "patterns": [pattern],
            "concepts": concepts,
            "locator": f"Page 1, task {number}",
        }
        return value | extra

    observer_statement = [
        text(
            "Question 1",
            "exam-ws23",
            "A weather station measures temperature. Several displays must update whenever a "
            "new measurement arrives, and new displays will be added later without changing "
            "the station. Design the classes and explain how updates reach each display.",
        )
    ]
    solution = {
        "origin": "official",
        "official_source": "exam-ws23-solution",
        "blocks": [text("Solution", "exam-ws23-solution", "The station is the subject.")],
    }
    return {
        "schema_version": 1,
        "course_key": state.course.key,
        "profile": {
            "format": "written",
            "duration_minutes": 90,
            "total_points": 40,
            "allowed_aids": "One handwritten A4 sheet.",
            "languages": ["English"],
            "question_formats": ["code", "short"],
            "sources": [ref("slides")],
        },
        "topics": [
            {"key": "behavioral", "title": "Behavioral patterns", "order": 1},
            {"key": "structural", "title": "Structural patterns", "order": 2},
        ],
        "sittings": [
            {
                "key": "ws23",
                "label": "Endterm WS23/24",
                "held": "2024-02",
                "kind": "final",
                "variants": [
                    {
                        "key": "ws23-a",
                        "label": "Group A",
                        "sources": [
                            role("exam-ws23"),
                            role("exam-ws23-solution", "official_solution"),
                        ],
                        "total_points": 20,
                        "questions": [
                            question(
                                "ws23-a-1",
                                "1",
                                "observer-design",
                                ["observer", "loose-coupling"],
                                "exam-ws23",
                                statement=observer_statement,
                                solution=solution,
                                marking=[
                                    {"text": "Subject interface", "points": 4},
                                    {"text": "Notify loop", "points": 6},
                                ],
                                marking_basis="official",
                            ),
                            question("ws23-a-2", "2", "strategy-swap", ["strategy"], "exam-ws23"),
                        ],
                    },
                    {
                        "key": "ws23-b",
                        "label": "Group B",
                        "sources": [role("exam-ws23-b")],
                        "questions": [
                            question(
                                "ws23-b-1", "1", "observer-design", ["observer"], "exam-ws23-b"
                            ),
                            question("ws23-b-2", "2", "strategy-swap", ["strategy"], "exam-ws23-b"),
                        ],
                    },
                ],
            },
            {
                "key": "ws22",
                "label": "Endterm WS22/23",
                "held": "2023-02",
                "kind": "final",
                "variants": [
                    {
                        "key": "ws22-a",
                        "label": "Exam",
                        "sources": [role("exam-ws22"), role("exam-ws22-upload")],
                        "questions": [
                            question("ws22-1", "1", "observer-design", ["observer"], "exam-ws22"),
                            question(
                                "ws22-2",
                                "2",
                                "composite-tree",
                                ["composite"],
                                "exam-ws22",
                                points=None,
                                confidence="low",
                            ),
                        ],
                    }
                ],
            },
            {
                "key": "ss19",
                "label": "Retake SS19",
                "held": "2019",
                "kind": "retake",
                "relevance": "outdated",
                "relevance_note": "Different lecturer and syllabus.",
                "variants": [
                    {
                        "key": "ss19-a",
                        "label": "Exam",
                        "sources": [role("exam-ss19")],
                        "questions": [
                            {
                                "key": "ss19-1",
                                "number": "1",
                                "format": "short",
                                "status": "out_of_scope",
                                "reason": "Singleton is no longer taught.",
                                "locator": "Page 1",
                            }
                        ],
                    }
                ],
            },
        ],
        "concepts": [
            {
                "key": "observer",
                "topic": "behavioral",
                "title": "Observer",
                "kind": "definition",
                "line": "A subject notifies registered observers when its state changes.",
                "trigger": "Several views must update when one object changes.",
                "basis": "tested",
                "sources": [ref("slides")],
                "details": [text("Structure", "slides", "Subject keeps a list of observers.")],
            },
            {
                "key": "loose-coupling",
                "topic": "behavioral",
                "title": "Loose coupling",
                "kind": "fact",
                "line": "Depend on interfaces, not concrete classes.",
                "basis": "prerequisite",
                "sources": [ref("slides")],
            },
            {
                "key": "strategy",
                "topic": "behavioral",
                "title": "Strategy",
                "kind": "definition",
                "line": "Encapsulate interchangeable algorithms behind one interface.",
                "basis": "tested",
                "sources": [ref("slides")],
            },
            {
                "key": "composite",
                "topic": "structural",
                "title": "Composite",
                "kind": "definition",
                "line": "Treat single objects and compositions uniformly in a tree.",
                "basis": "tested",
                "sources": [ref("slides")],
            },
            {
                "key": "decorator",
                "topic": "structural",
                "title": "Decorator",
                "kind": "definition",
                "line": "Add responsibilities by wrapping an object with the same interface.",
                "basis": "untested_core",
                "sources": [ref("slides")],
            },
            {
                "key": "cohesion",
                "topic": "structural",
                "title": "Cohesion metric",
                "kind": "formula",
                "line": "LCOM counts method pairs without shared fields.",
                "formula": {
                    "latex": "LCOM = |P| - |Q|",
                    "plain": "LCOM equals P minus Q",
                    "symbols": [{"symbol": "P", "meaning": "pairs sharing no field"}],
                },
                "basis": "emphasized",
                "on_map": False,
                "sources": [ref("slides")],
            },
        ],
        "links": [
            {"start": "loose-coupling", "end": "observer", "kind": "requires"},
            {"start": "loose-coupling", "end": "strategy", "kind": "requires"},
            {
                "start": "composite",
                "end": "decorator",
                "kind": "contrasts",
                "note": "Both wrap; only Composite aggregates.",
            },
        ],
        "patterns": [
            {
                "key": "observer-design",
                "topic": "behavioral",
                "title": "Design an Observer",
                "summary": "Model one-to-many update notification.",
                "cues": ["Several displays update after one change", "New listeners added later"],
                "workflow": [
                    {"do": "Name the subject and observers", "why": "Roles fix dependencies."},
                    {"do": "Define the observer interface"},
                    {"do": "Register, unregister and notify"},
                ],
                "marking": ["Interface defined", "Notify loop"],
                "marking_basis": "official",
                "concepts": ["observer", "loose-coupling"],
                "sources": [ref("slides")],
                "example": {"question": "ws23-a-1"},
                "drill": [
                    {
                        "key": "d1",
                        "prompt": "Which class holds the observer list?",
                        "check": {
                            "kind": "text",
                            "accepted": ["Subject", "the subject"],
                            "case_sensitive": False,
                            "feedback": "The object that changes owns the list.",
                        },
                        "explanation": "The subject owns registrations.",
                    }
                ],
            },
            {
                "key": "strategy-swap",
                "topic": "behavioral",
                "title": "Swap an algorithm",
                "summary": "Replace conditionals by interchangeable strategies.",
                "cues": ["A method switches on a mode flag"],
                "workflow": [{"do": "Extract a strategy interface"}],
                "concepts": ["strategy"],
                "sources": [ref("slides")],
            },
            {
                "key": "composite-tree",
                "topic": "structural",
                "title": "Build a part-whole tree",
                "summary": "Model recursive containment.",
                "cues": ["Folders contain files and folders"],
                "workflow": [{"do": "Give leaves and composites one component interface"}],
                "concepts": ["composite"],
                "sources": [ref("slides")],
            },
        ],
        "mocks": [
            {
                "key": "forecast-1",
                "title": "Practice exam 1",
                "duration_minutes": 90,
                "instructions": "Answer all questions.",
                "sources": [ref("slides")],
                "questions": [
                    {
                        "key": "f1-1",
                        "number": "1",
                        "points": 10,
                        "format": "code",
                        "patterns": ["observer-design"],
                        "concepts": ["observer"],
                        "novelty": "variant",
                        "varies_from": ["ws23-a-1"],
                        "change": "representation",
                        "change_note": "Given as a sequence diagram instead of prose.",
                        "statement": [
                            text(
                                "Question 1",
                                "slides",
                                "Implement the chat room notification from its sequence diagram.",
                            )
                        ],
                        "marking": [{"text": "Notification implemented", "points": 10}],
                        "minutes": 20,
                        "difficulty": 2,
                        "solution": {"blocks": [text("Solution", "slides", "Loop over members.")]},
                    },
                    {
                        "key": "f1-2",
                        "number": "2",
                        "points": 8,
                        "format": "short",
                        "concepts": ["decorator"],
                        "novelty": "untested",
                        "statement": [
                            text(
                                "Question 2",
                                "slides",
                                "Contrast a logging decorator with a logging subclass.",
                            )
                        ],
                        "check": {
                            "kind": "choice",
                            "options": [
                                {"key": "a", "text": "Wraps at runtime", "feedback": "Yes."},
                                {"key": "b", "text": "Copies the class", "feedback": "No."},
                                {"key": "c", "text": "Needs reflection", "feedback": "No."},
                                {"key": "d", "text": "Changes the interface", "feedback": "No."},
                            ],
                            "correct": "a",
                        },
                        "marking": [
                            {"text": "Runtime wrapping", "points": 4, "auto": True},
                            {"text": "Same interface", "points": 4},
                        ],
                        "minutes": 10,
                        "difficulty": 1,
                        "solution": {
                            "blocks": [text("Solution", "slides", "Decorators wrap at runtime.")]
                        },
                    },
                ],
            }
        ],
    }


def with_guided_paper(document: dict) -> dict:
    """Make WS23 Group A replayable, with a text step and an order step to practise."""
    variant = document["sittings"][0]["variants"][0]
    second = variant["questions"][1]
    second["statement"] = [
        text("Question 2", "exam-ws23", "A sorter switches on a mode string. Refactor it.")
    ]
    second["solution"] = {
        "origin": "authored",
        "blocks": [text("Solution", "exam-ws23", "Introduce a SortStrategy interface.")],
    }
    variant["questions"][0]["guidance"] = {
        "objectives": ["Separate the changing part from the stable part."],
        "steps": [
            {
                "key": "roles",
                "purpose": "Identify roles",
                "prompt": "Which object changes state?",
                "hints": ["Look for whenever."],
                "check": {
                    "kind": "text",
                    "accepted": ["station", "the station", "weather station"],
                    "case_sensitive": False,
                    "feedback": "The object whose state changes is the subject.",
                },
                "explanation": "The station is the subject; displays observe it.",
            },
            {
                "key": "order",
                "purpose": "Order the notification",
                "prompt": "Order the lines of notify().",
                "check": {
                    "kind": "order",
                    "language": "java",
                    "items": [
                        {"key": "a", "code": "for (Observer o : observers) {"},
                        {"key": "b", "code": "  o.update(temperature);"},
                        {"key": "c", "code": "}"},
                        {"key": "d", "code": "observers.clear();"},
                    ],
                    "answers": [["a", "b", "c"]],
                    "feedback": "Loop over observers and update each one.",
                },
                "explanation": "Iterate and update; never clear registrations.",
            },
        ],
    }
    return document
