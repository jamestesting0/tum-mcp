"""What a review reads: every reviewed item, its passages and the fingerprint of each block.

A verdict stays current while the blocks it covers keep their fingerprints, so an edit
re-opens exactly the checks that could have changed.
"""

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.course.content.study import term_markers
from tum_mcp.course.project.store import confined, read_bytes
from tum_mcp.course.review.models import SHEET, item_passages, sheet_model
from tum_mcp.errors import CampusError, Code


def digest(value: JsonValue) -> str:
    body = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ReviewItem:
    key: str
    profile: str
    title: str
    value: dict
    blocks: dict[str, str] = field(default_factory=dict)
    preparation: str | None = None
    annotations: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, JsonValue] = field(default_factory=dict)

    def passages(self) -> list[tuple[str, str]]:
        return item_passages(self.value)


def resolve_item(items: dict[str, ReviewItem], item: str) -> str:
    """The item named exactly, or the one item whose key ends with it (`dfs` for study/dfs)."""
    if item in items:
        return item
    matches = [key for key in items if key.endswith("/" + item)]
    if len(matches) == 1:
        return matches[0]
    known = sorted(items)
    listed = ", ".join(known[:15]) + (f" and {len(known) - 15} more" if len(known) > 15 else "")
    raise CampusError(Code.ACTION_REQUIRED, f"No item {item}; the items are {listed or 'none'}.")


def blocks_of(value: dict) -> dict[str, str]:
    """Fingerprint each field, each list element, and the order of list elements."""
    result: dict[str, str] = {}
    for name, item in value.items():
        if isinstance(item, list):
            order = []
            for index, element in enumerate(item):
                label = element.get("key") if isinstance(element, dict) else None
                block = f"{name}:{label}" if isinstance(label, str) else f"{name}:{index}"
                if block in result:
                    block = f"{name}:{index}"
                result[block] = digest(element)
                order.append(block)
            result[f"@{name}:order"] = digest(order)
        else:
            result[name] = digest(item)
    return result


def answer_key(root: Path, key: str) -> str | None:
    body = read_bytes(confined(root, f".tum-mcp/checks/{key}.py"))
    return hashlib.sha256(body).hexdigest()[:16] if body is not None else None


# Cross-workspace links: reviewed with the course's link matrix, so adding a link to an older
# item (a new lecture's lesson) never marks that item's teaching as changed.
LINK_FIELDS = frozenset({"prerequisites", "lectures", "units", "passages", "exercises", "passage"})


def _without_links(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {k: _without_links(v) for k, v in value.items() if k not in LINK_FIELDS}
    if isinstance(value, list):
        return [_without_links(entry) for entry in value]
    return value


def _item(root: Path, key: str, profile: str, title: str, value: dict) -> ReviewItem:
    blocks = blocks_of(_without_links(value))
    if script := answer_key(root, key):
        blocks["answer-key"] = script
    return ReviewItem(key, profile, title, value, blocks)


def collect(
    root: Path,
    *,
    content=None,
    exercises=None,
    exam=None,
    lectures=None,
    ledger=None,
) -> dict[str, ReviewItem]:
    items: dict[str, ReviewItem] = {}
    glossary = (
        {entry.term.lower(): entry.meaning for entry in content.annotations} if content else {}
    )

    def add(key: str, profile: str, title: str, value: dict) -> None:
        item = _item(root, key, profile, title, value)
        if glossary and profile in {"study-unit", "exercise"}:
            used = {
                term: glossary[term]
                for term in sorted(term_markers(value, fold=False) & glossary.keys())
            }
            if used:
                item = replace(
                    item, blocks=item.blocks | {"@annotations": digest(used)}, annotations=used
                )
        items[key] = item

    for unit in content.units if content else ():
        add(f"study/{unit.key}", "study-unit", unit.title, unit.model_dump(mode="json"))
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            add(
                f"exercises/{group.key}/{exercise.key}",
                "exercise",
                exercise.title,
                exercise.model_dump(mode="json"),
            )
    if exam is not None:
        from tum_mcp.course.content.exam import CONSIDERED

        past = exam.past_questions()
        for pattern in exam.patterns:
            value = pattern.model_dump(mode="json")
            referenced = {example.question for example in pattern.examples if example.question}
            value["past_questions"] = [
                question.model_dump(mode="json")
                | {"source_versions": [s.model_dump(mode="json") for s in variant.sources]}
                for sitting, variant, question in past.values()
                if question.key in referenced
                or (
                    sitting.relevance in CONSIDERED
                    and question.status == "classified"
                    and pattern.key in question.patterns
                )
            ]
            add(
                f"exam/pattern/{pattern.key}",
                "exam-pattern",
                pattern.title,
                value,
            )
        if exam.concepts:
            add(
                SHEET, "exam-sheet", "Cheatsheet", sheet_model(exam, ledger).model_dump(mode="json")
            )
        for mock in exam.mocks:
            for question in mock.questions:
                add(
                    f"exam/mock/{mock.key}/{question.key}",
                    "exam-mock-question",
                    f"{mock.title} · Question {question.number}",
                    question.model_dump(mode="json"),
                )
    for lecture in lectures.lectures if lectures else ():
        from tum_mcp.course.lecture.selection import selection_item

        selection = selection_item(root, lecture)
        items[selection.key] = selection
        for entry in lecture.entries:
            add(
                f"lecture/{lecture.key}/{entry.key}",
                "lecture-entry",
                entry.title,
                entry.model_dump(mode="json"),
            )
    return items


def course_item(structure: dict, revision: str, knowledge: str | None = None) -> ReviewItem:
    """The course as one item: its map is read; its structure revision, and the reviewed
    Course Memory relations when enabled, decide staleness."""
    blocks = {"structure": revision} | ({"knowledge": knowledge[:16]} if knowledge else {})
    return ReviewItem("course", "course", "Course", structure, blocks)
