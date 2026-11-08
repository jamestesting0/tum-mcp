"""Cross-workspace links: every exercise, cheatsheet entry, lecture note and Study unit either
links each existing target workspace or records why none fits, so Recall never depends on the
author remembering which workspace was prepared second."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, JsonValue

from tum_mcp.course.content.exam import ExamContent
from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.study import StudyContent
from tum_mcp.course.lecture.content import LectureContent
from tum_mcp.course.project.models import Key
from tum_mcp.course.project.store import Write, apply, private_name, read_bytes
from tum_mcp.course.review.items import digest
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

Target = str
TARGETS = ("study", "cheatsheet", "exercises", "lectures")
WORDS = re.compile(r"[a-z][a-z-]{3,}")


class Decision(Frozen):
    item: str = Field(min_length=1, max_length=300)
    target: Key
    reason: str = Field(min_length=10, max_length=300)
    # The target workspace's outline when decided; a new unit or entry reopens the decision.
    outline: str


class Decisions(Frozen):
    decisions: tuple[Decision, ...] = ()


@dataclass(frozen=True, slots=True)
class Linkable:
    item: str
    title: str
    target: Target
    linked: bool


def outlines(
    study: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    lectures: LectureContent | None,
) -> dict[Target, str]:
    """A digest of each existing target workspace's entries; absent workspaces are left out."""
    found: dict[Target, JsonValue] = {}
    if study and study.units:
        found["study"] = [[u.key, [b.key for b in u.blocks if b.key]] for u in study.units]
    if exam and exam.concepts:
        found["cheatsheet"] = [concept.key for concept in exam.concepts]
    if exercises and any(group.exercises for group in exercises.sets):
        found["exercises"] = [[g.key, [e.key for e in g.exercises]] for g in exercises.sets]
    if lectures and any(lecture.notes for lecture in lectures.lectures):
        found["lectures"] = [lecture.key for lecture in lectures.lectures if lecture.notes]
    return {target: digest(value) for target, value in found.items()}


def linkables(
    study: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    lectures: LectureContent | None,
) -> list[Linkable]:
    """Each (item, target workspace) pair that needs a decision, and whether it is linked."""
    present = outlines(study, exercises, exam, lectures)
    listed = {
        (link.set, link.exercise)
        for concept in (exam.concepts if exam else ())
        for link in concept.exercises
    }
    pairs: list[Linkable] = []
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            item = f"exercises/{group.key}/{exercise.key}"
            if "study" in present:
                pairs.append(Linkable(item, exercise.title, "study", bool(exercise.prerequisites)))
            if "cheatsheet" in present:
                linked = (group.key, exercise.key) in listed
                pairs.append(Linkable(item, exercise.title, "cheatsheet", linked))
    for concept in exam.concepts if exam else ():
        item = f"concept:{concept.key}"
        if "study" in present:
            pairs.append(
                Linkable(item, concept.title, "study", bool(concept.units or concept.passages))
            )
        if "exercises" in present:
            pairs.append(Linkable(item, concept.title, "exercises", bool(concept.exercises)))
    for lecture in lectures.lectures if lectures else ():
        for note in lecture.notes:
            if "study" in present:
                item = f"lecture/{lecture.key}/{note.key}"
                pairs.append(Linkable(item, note.title, "study", note.passage is not None))
    for unit in study.units if study else ():
        if "lectures" in present:
            pairs.append(Linkable(f"study/{unit.key}", unit.title, "lectures", bool(unit.lectures)))
    return pairs


def read_decisions(root: Path) -> Decisions:
    body = read_bytes(root / private_name(root, "links.json"))
    return Decisions.model_validate_json(body) if body else Decisions()


def undecided(root: Path, study, exercises, exam, lectures) -> list[Linkable]:
    """Unlinked pairs without a current "none" decision."""
    present = outlines(study, exercises, exam, lectures)
    current = {
        (decision.item, decision.target)
        for decision in read_decisions(root).decisions
        if present.get(decision.target) == decision.outline
    }
    return [
        pair
        for pair in linkables(study, exercises, exam, lectures)
        if not pair.linked and (pair.item, pair.target) not in current
    ]


def _titles(study, exercises, exam, lectures, target: Target) -> list[tuple[str, str]]:
    if target == "study" and study:
        return [
            (f"{unit.key}#{block.key}" if block.key else unit.key, block.title or unit.title)
            for unit in study.units
            for block in (*unit.blocks[:1], *(b for b in unit.blocks if b.title and b.key))
        ]
    if target == "cheatsheet" and exam:
        return [(concept.key, concept.title) for concept in exam.concepts]
    if target == "exercises" and exercises:
        return [(f"{g.key}/{e.key}", e.title) for g in exercises.sets for e in g.exercises]
    if target == "lectures" and lectures:
        return [(lecture.key, lecture.title) for lecture in lectures.lectures if lecture.notes]
    return []


def hints(title: str, candidates: list[tuple[str, str]]) -> list[str]:
    """Up to three targets sharing words with the item's title, best first."""
    words = set(WORDS.findall(title.lower()))
    scored = sorted(
        ((len(words & set(WORDS.findall(name.lower()))), key) for key, name in candidates),
        reverse=True,
    )
    return list(dict.fromkeys(key for score, key in scored if score))[:3]


def report(root: Path, study, exercises, exam, lectures) -> dict[str, JsonValue]:
    open_pairs = undecided(root, study, exercises, exam, lectures)
    return {
        "undecided": [
            {
                "item": pair.item,
                "target": pair.target,
                "hints": hints(pair.title, _titles(study, exercises, exam, lectures, pair.target)),
            }
            for pair in open_pairs
        ],
        "next": (
            "Link each one in its content (exercise prerequisites, concept units or passages, "
            "concept exercises, note passage, unit lectures), or record that none fits: "
            "tum-mcp study links PROJECT --none ITEM --target TARGET --reason TEXT."
            if open_pairs
            else "Every item is linked or has a current reason."
        ),
    }


def record_none(root: Path, study, exercises, exam, lectures, item: str, target: str, reason: str):
    present = outlines(study, exercises, exam, lectures)
    pairs = {(pair.item, pair.target) for pair in linkables(study, exercises, exam, lectures)}
    if (item, target) not in pairs:
        raise CampusError(Code.ACTION_REQUIRED, f"{item} needs no {target} link decision.")
    kept = [d for d in read_decisions(root).decisions if (d.item, d.target) != (item, target)]
    decision = Decision(item=item, target=target, reason=reason, outline=present[target])
    body = Decisions(decisions=(*kept, decision)).model_dump_json(indent=2).encode()
    name = private_name(root, "links.json")
    apply(root, (Write(name, read_bytes(root / name), body),))
    return json.loads(decision.model_dump_json())
