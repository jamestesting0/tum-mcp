"""The parts of a course item that a video or an audio track presents.

Media never add teaching: each one presents an existing Study unit, exercise, Exam pattern or
cheatsheet concept. Every required part is either covered by a beat or chapter, or left to the
page with a reason. Audio and video address a part the same way and fingerprint it with the
same function, so a locator means the same thing in both.
"""

from tum_mcp.course.content.exam import Concept, ExamContent, Pattern
from tum_mcp.course.content.exercises import Exercise, ExerciseContent
from tum_mcp.course.content.study import StudyContent, Unit
from tum_mcp.course.media.video_content import (
    Locator,
    _teaching,
    canonical,
    fingerprint,
    locator_fingerprint,
    semantic_hash,
    sha256,
)
from tum_mcp.settings import Frozen

Item = Unit | Exercise | Pattern | Concept


def exercise_hash(exercise: Exercise) -> str:
    value = exercise.model_dump(
        mode="json",
        exclude_none=True,
        exclude={"label", "title", "sources", "kind", "distilled_from", "objectives", "transfer"},
    )
    for step in value["steps"]:
        step.pop("hints", None)
    for name in ("origin", "official_source"):
        value["solution"].pop(name, None)
    return sha256(canonical(_teaching(value)))


def _exam_hash(item: Concept | Pattern) -> str:
    return sha256(canonical(item.model_dump(mode="json", exclude={"sources"}, exclude_none=True)))


def teaching_hash(item: Item) -> str:
    """The item's teaching identity; a change makes media made from it stale."""
    match item:
        case Unit():
            return semantic_hash(item)
        case Exercise():
            return exercise_hash(item)
        case Pattern() | Concept():
            return _exam_hash(item)


def find(
    study: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    kind: str,
    key: str,
    group: str | None = None,
) -> Item | None:
    """The current item a medium names, or None when it was removed or moved."""
    match kind:
        case "unit":
            units = study.units if study else ()
            return next((unit for unit in units if unit.key == key), None)
        case "exercise":
            sets = exercises.sets if exercises else ()
            return next(
                (e for s in sets if s.key == group for e in s.exercises if e.key == key), None
            )
        case "concept":
            return next((c for c in (exam.concepts if exam else ()) if c.key == key), None)
        case "pattern":
            return next((p for p in (exam.patterns if exam else ()) if p.key == key), None)
        case _:
            return None


def source_kind(item: Item) -> str:
    match item:
        case Unit():
            return "unit"
        case Exercise():
            return "exercise"
        case Pattern():
            return "pattern"
        case Concept():
            return "concept"


def _index(ref: str, prefix: str) -> int | None:
    head, _, rest = ref.partition("[")
    if head != prefix or not rest.endswith("]") or not rest[:-1].isdigit():
        return None
    return int(rest[:-1])


def _pattern_part(pattern: Pattern, kind: str, ref: str) -> Frozen | str | tuple[str, ...] | None:
    match kind:
        case "cue" | "variation" | "pitfall" | "example" | "workflow":
            field, values = {
                "cue": ("cues", pattern.cues),
                "variation": ("variations", pattern.variations),
                "pitfall": ("pitfalls", pattern.pitfalls),
                "example": ("examples", pattern.examples),
                "workflow": ("workflow", pattern.workflow),
            }[kind]
            index = _index(ref, field)
            return values[index] if index is not None and index < len(values) else None
        case "case":
            step_ref, _, case_ref = ref.partition(".")
            step, case = _index(step_ref, "workflow"), _index(case_ref, "cases")
            if step is None or case is None or step >= len(pattern.workflow):
                return None
            cases = pattern.workflow[step].cases
            return cases[case] if case < len(cases) else None
        case "marking":
            return pattern.marking if ref == "marking" and pattern.marking else None
        case _:
            return None


def _exercise_part(exercise: Exercise, kind: str, ref: str) -> Frozen | None:
    match kind:
        case "statement":
            index = _index(ref, "statement")
            values = exercise.statement
        case "answer":
            index = _index(ref, "answers")
            values = exercise.solution.answers
        case "step":
            return next((step for step in exercise.steps if step.key == ref), None)
        case _:
            return None
    return values[index] if index is not None and index < len(values) else None


def part_fingerprint(item: Item, kind: str, ref: str) -> str | None:
    """The current fingerprint of one part, or None when the item no longer has it."""
    match item:
        case Unit():
            probe = Locator.model_validate({"kind": kind, "ref": ref, "fingerprint": "0" * 64})
            return locator_fingerprint(item, probe)
        case Exercise():
            value = _exercise_part(item, kind, ref)
            if value is None:
                return None
            if kind == "step":
                data = value.model_dump(mode="json", exclude_none=True, exclude={"hints"})
                return sha256(canonical(_teaching(data)))
            return fingerprint(value)
        case Pattern():
            if kind == "pattern":
                return _exam_hash(item) if ref == item.key else None
            value = _pattern_part(item, kind, ref)
            if value is None:
                return None
            if isinstance(value, Frozen):
                return fingerprint(value)
            return sha256(canonical(list(value) if isinstance(value, tuple) else value))
        case Concept():
            return _exam_hash(item) if kind == "concept" and ref == item.key else None


def required_parts(item: Item) -> tuple[tuple[str, str], ...]:
    """Every part the media must present or leave to the page, in reading order."""
    match item:
        case Unit():
            return (
                *(("block", f"blocks[{i}]") for i in range(len(item.blocks))),
                *(("objective", objective.key) for objective in item.objectives),
            )
        case Exercise():
            return (
                *(("statement", f"statement[{i}]") for i in range(len(item.statement))),
                *(("step", step.key) for step in item.steps),
                *(("answer", f"answers[{i}]") for i in range(len(item.solution.answers))),
            )
        case Pattern():
            # Drills are never required: solving them on screen or aloud spoils the practice.
            parts: list[tuple[str, str]] = [("cue", f"cues[{i}]") for i in range(len(item.cues))]
            for i, step in enumerate(item.workflow):
                parts.append(("workflow", f"workflow[{i}]"))
                parts.extend(("case", f"workflow[{i}].cases[{j}]") for j in range(len(step.cases)))
            if item.marking:
                parts.append(("marking", "marking"))
            parts.extend(("pitfall", f"pitfalls[{i}]") for i in range(len(item.pitfalls)))
            parts.extend(("variation", f"variations[{i}]") for i in range(len(item.variations)))
            parts.extend(("example", f"examples[{i}]") for i in range(len(item.examples)))
            return tuple(parts)
        case Concept():
            return (("concept", item.key),)


def parts(item: Item) -> list[dict[str, str]]:
    return [
        {"kind": kind, "ref": ref, "fingerprint": part_fingerprint(item, kind, ref) or ""}
        for kind, ref in required_parts(item)
    ]


def missing(item: Item, covered: set[tuple[str, str]], left: set[tuple[str, str]]) -> list[str]:
    return [
        f"{kind} {ref}"
        for kind, ref in required_parts(item)
        if (kind, ref) not in covered and (kind, ref) not in left
    ]
