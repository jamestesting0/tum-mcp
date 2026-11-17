"""The thread packet: what an Ask agent turn needs to know about the selected passage.

Built on the server from the anchor the page sends, never from page text: the agent sees the
authored source (with its LaTeX), the file and JSON location to edit, cited sources and the
course links around the passage. Everything else the agent reads with tools when it needs it.
"""

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from tum_mcp.course.app.comment_models import (
    Anchor,
    ExamAnchor,
    ExerciseAnchor,
    ExploreAnchor,
    LectureAnchor,
)
from tum_mcp.course.app.comments import keyed
from tum_mcp.course.content.store import read_document
from tum_mcp.course.project.paths import APP
from tum_mcp.course.project.store import confined, load_state, read_bytes
from tum_mcp.errors import CampusError

AnyAnchor = Anchor | ExploreAnchor | ExerciseAnchor | ExamAnchor | LectureAnchor
ANCHOR: TypeAdapter[AnyAnchor] = TypeAdapter(AnyAnchor)
LIMIT = 8 * 1024
SOURCE_LIMIT = 3000
Short = Annotated[str, Field(max_length=200)]


class View(BaseModel):
    """What the page shows around the selection, as the client reports it."""

    model_config = ConfigDict(extra="forbid")
    route: Short = ""
    step: Short = ""
    chosen: Short = ""
    correct: bool | None = None
    face: Short = ""
    draft: Annotated[str, Field(max_length=1000)] = ""


def _json(value: object, limit: int = SOURCE_LIMIT) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=1)
    return text if len(text) <= limit else text[:limit] + "\n… (truncated; read the file)"


def _file(root: Path, name: str) -> dict:
    body = read_bytes(confined(root, name))
    return json.loads(body) if body else {}


def _related(root: Path, ref: str) -> list[str]:
    """Up to six course links around the passage; a course without links has none."""
    from tum_mcp.course.relations.query import context

    try:
        packet = context(root, item=ref, limit=7, max_bytes=8000)
    except CampusError:
        return []
    relations = {
        path["target"]: path["steps"][-1]["relation"]
        for path in packet.get("paths", [])
        if path.get("steps")
    }
    return [
        f"{item.get('title') or item['id']} ({item['id']}, {relations[item['id']]})"
        for item in packet.get("items", [])
        if item["id"] in relations
    ][:6]


def anchor_file(anchor: AnyAnchor) -> str:
    """The authored file an anchor points into."""
    match anchor:
        case ExerciseAnchor():
            return f"{APP}/exercises/{anchor.set_key}/{anchor.exercise_key}.json"
        case ExamAnchor():
            kind, _, key = anchor.item_key.partition(":")
            folder = {"concept": "concepts", "pattern": "patterns", "mock": "mocks"}.get(kind)
            return f"{APP}/exam/{folder}/{key}.json" if folder else f"{APP}/exam/exam.json"
        case LectureAnchor():
            return f"{APP}/lectures/lectures/{anchor.lecture_key}.json"
        case _:
            return f"{APP}/study/units/{anchor.unit_key}.json"


def _place(root: Path, anchor: AnyAnchor) -> tuple[list[str], str]:
    name = anchor_file(anchor)
    match anchor:
        case ExerciseAnchor():
            exercise = _file(root, name)
            step = keyed(exercise.get("steps", []), anchor.step_key) if anchor.step_key else None
            lines = [
                f"workspace: Exercises · {exercise.get('label', '')} {exercise.get('title', '')}",
                f"file: {name} · field: {anchor.field}"
                + (f" · step {anchor.step_key}" if anchor.step_key else ""),
                "authored source of the selected step or exercise:",
                _json(step or exercise),
            ]
            return lines, f"exercises/set/{anchor.set_key}/exercise/{anchor.exercise_key}"
        case ExamAnchor():
            kind, _, key = anchor.item_key.partition(":")
            document = read_document(root, "exam") or {}
            item = keyed(document, key) or {}
            lines = [f"workspace: Exam · {kind} {item.get('title', key)}"]
            if kind == "mock":
                lines.append(
                    "set: untimed practice set"
                    if item.get("kind") == "practice"
                    else f"set: timed mock exam, {item.get('duration_minutes')} minutes"
                )
            lines += [
                f"file: {name} · field: {anchor.field}",
                "authored source:",
                _json(item),
            ]
            return lines, f"exam/{kind}/{key}"
        case LectureAnchor():
            lecture = _file(root, name)
            section = keyed(lecture, anchor.section_key) or {}
            lines = [
                f"workspace: Lecture · {lecture.get('title', anchor.lecture_key)}",
                f"file: {name} · section {anchor.section_key}",
                "authored source of the section:",
                _json(section),
            ]
            return lines, f"lectures/lecture/{anchor.lecture_key}/section/{anchor.section_key}"
        case ExploreAnchor():
            unit = _file(root, name)
            item = keyed(unit.get("explore", []), anchor.item_key) or {}
            block = keyed(item.get("blocks", []), anchor.block_key) or {}
            lines = [
                f"workspace: Study (Explore) · {unit.get('title', '')} · {item.get('title', '')}",
                f"file: {name} · explore item {anchor.item_key} · block {anchor.block_key}",
                "authored source of the block:",
                _json(block),
            ]
            return lines, f"study/unit/{anchor.unit_key}/explore/{anchor.item_key}"
        case Anchor():
            unit = _file(root, name)
            blocks = unit.get("blocks", [])
            if anchor.view == "content":
                block = blocks[anchor.block_index] if anchor.block_index < len(blocks) else {}
                titles = [
                    ("> " if index == anchor.block_index else "") + item["title"]
                    for index, item in enumerate(blocks)
                    if item.get("title")
                ]
                lines = [
                    f"workspace: Study · {unit.get('title', '')}",
                    "sections: " + " | ".join(titles),
                    f"file: {name} · blocks[{anchor.block_index}] (key {block.get('key')})",
                ]
                if block.get("sources"):
                    lines.append(
                        f"cited: {', '.join(block['sources'])} · pages {block.get('pages', '?')}"
                    )
                lines += ["authored source of the section:", _json(block)]
                ref = f"study/unit/{anchor.unit_key}" + (
                    f"/block/{block['key']}" if block.get("key") else ""
                )
                return lines, ref
            field = "flashcards" if anchor.view == "flashcards" else "questions"
            item = keyed(unit.get(field, []), anchor.item_key or "") or {}
            lines = [
                f"workspace: Study {anchor.view} · {unit.get('title', '')}",
                f"file: {name} · {field} item {anchor.item_key} · field {anchor.field}",
                "authored source:",
                _json(item),
            ]
            return lines, f"study/unit/{anchor.unit_key}"
    return [], ""


def location(anchor: AnyAnchor) -> str:
    """Where an anchor points, without its quote: equal for two passages of one section."""
    fields = anchor.model_dump(mode="json", exclude={"quote", "prefix", "suffix"})
    return json.dumps(fields, sort_keys=True)


def packet(
    root: Path,
    anchor: AnyAnchor | None,
    view: View,
    comments: list[str],
    *,
    section: bool = False,
    quote: str = "",
    brief: bool = False,
) -> str:
    """The context for a turn. `section` marks the section in view instead of a selection;
    `brief` is a follow-up's packet, which leaves out the course and its related items."""
    lines: list[str] = []
    if not brief:
        course = load_state(root).course
        lines.append(f"course: {course.title} ({course.semester})")
    if view.route:
        lines.append(f"page: #{view.route}")
    if anchor is not None:
        place, ref = _place(root, anchor)
        lines.append(
            "context: the section in view"
            if section
            else f'selected text: "{quote or anchor.quote}"'
        )
        lines += place
        if not brief and ref and (related := _related(root, ref)):
            lines.append("related: " + "; ".join(related))
    state = [
        f"{label}: {value}"
        for label, value in (
            ("guide step", view.step),
            ("chosen option", view.chosen),
            ("flashcard face", view.face),
        )
        if value
    ]
    if view.correct is not None:
        state.append(f"answered correctly: {'yes' if view.correct else 'no'}")
    if view.draft:
        state.append(f"student's draft: {view.draft}")
    if state:
        lines.append("student state: " + " · ".join(state))
    if comments:
        lines.append("open comments here: " + " | ".join(comments[:3]))
    text = "\n".join(lines)
    return "<course-app-context>\n" + text[:LIMIT] + "\n</course-app-context>"
