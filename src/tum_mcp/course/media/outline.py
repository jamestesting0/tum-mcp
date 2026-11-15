"""Draft storyboards and track scripts whose beats and chapters already address every required
part of their source item. The author writes the words, the pictures and the scene code; each
text still to write starts with the placeholder, and the checks refuse it until it is replaced."""

import json
from itertools import islice
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.course.content.exam import Pattern
from tum_mcp.course.content.exercises import Exercise
from tum_mcp.course.content.study import Unit
from tum_mcp.course.media.sources import Item, find, part_fingerprint, required_parts, teaching_hash
from tum_mcp.course.media.speech import PLACEHOLDER, unwritten
from tum_mcp.errors import CampusError, Code

Json = dict[str, JsonValue]


def _locator(item: Item, kind: str, ref: str) -> Json:
    return {"kind": kind, "ref": ref, "fingerprint": part_fingerprint(item, kind, ref) or ""}


def _chunks(values: list[Json], size: int = 20) -> list[list[Json]]:
    it = iter(values)
    return [chunk for chunk in iter(lambda: list(islice(it, size)), [])] or [[]]


class _Beats:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, kind: str, locators: list[Json], what: str, **extra: JsonValue) -> Json:
        self.count += 1
        beat: Json = {
            "key": f"b{self.count:02d}",
            "kind": kind,
            "narration": [f"{PLACEHOLDER} say {what}."],
            "intent": f"{PLACEHOLDER} what the picture shows while saying {what}.",
            "locators": locators,
        }
        shown = extra.pop("shown", 0)
        if isinstance(shown, int) and shown:
            beat["on_screen"] = [
                {"key": f"{beat['key']}-{i}", "kind": "label", "text": f"{PLACEHOLDER} {what}"}
                for i in range(shown)
            ]
        return beat | extra


def _chapters(groups: list[tuple[str, list[Json], Json]]) -> list[Json]:
    return [
        {"key": f"c{n:02d}", "title": title, "beats": beats, **extra}
        for n, (title, beats, extra) in enumerate(groups, 1)
    ]


def _unit(unit: Unit, beat: _Beats) -> Json:
    sections: list[list[int]] = []
    for index, block in enumerate(unit.blocks):
        if not sections or (getattr(block, "title", None) and len(sections) < 10):
            sections.append([index])
        else:
            sections[-1].append(index)
    point = f"{PLACEHOLDER} name the knowledge point"
    overview = [_locator(unit, "summary", "summary")] + [
        _locator(unit, "objective", objective.key) for objective in unit.objectives
    ]
    groups: list[tuple[str, list[Json], Json]] = [
        (
            "Overview",
            [
                beat("overview", chunk, "the question this lesson answers")
                for chunk in _chunks(overview)
            ],
            {},
        )
    ]
    for section in sections:
        first = unit.blocks[section[0]]
        title = getattr(first, "title", None) or f"{PLACEHOLDER} chapter title"
        beats = [
            beat(
                "instance" if unit.blocks[i].kind in {"example", "walkthrough"} else "mechanism",
                [_locator(unit, "block", f"blocks[{i}]")],
                f"what blocks[{i}] teaches",
                point=point,
            )
            for i in section
        ]
        groups.append((str(title)[:150], beats, {}))
    groups.append(
        ("Recap", [beat("recap", [_locator(unit, "summary", "summary")], "the taught results")], {})
    )
    return {
        "unit": unit.key,
        "unit_hash": teaching_hash(unit),
        "objectives": [objective.key for objective in unit.objectives],
        "chapters": _chapters(groups),
    }


def _exercise(exercise: Exercise, group: str, beat: _Beats) -> Json:
    statement = [
        _locator(exercise, "statement", f"statement[{i}]") for i in range(len(exercise.statement))
    ]
    groups: list[tuple[str, list[Json], Json]] = [
        (
            "The problem",
            [beat("setup", chunk, "the givens and what is asked") for chunk in _chunks(statement)],
            {},
        )
    ]
    answers = exercise.solution.answers
    for index, answer in enumerate(answers):
        label = getattr(answer, "label", None)
        steps = [s for s in exercise.steps if s.part == label] or (
            list(exercise.steps) if len(answers) == 1 else []
        )
        target = _locator(exercise, "answer", f"answers[{index}]")
        method = [_locator(exercise, "step", steps[0].key)] if steps else [target]
        beats = [
            beat("setup", [target], "what this part asks"),
            beat("strategy", method, "the method and why it fits"),
        ]
        beats += [
            beat("work", [_locator(exercise, "step", s.key)], f"the working of step {s.key}")
            for s in steps
        ] or [beat("work", [target], "the working")]
        beats += [
            beat("verify", [target], "how the result is checked"),
            beat("answer", [target], "the result"),
        ]
        title = f"Part {label}" if label else f"{PLACEHOLDER} chapter title"
        groups.append((str(title)[:150], beats, {"answer": target}))
    return {
        "exercise": {"set": group, "exercise": exercise.key},
        "exercise_hash": teaching_hash(exercise),
        "answers": [_locator(exercise, "answer", f"answers[{i}]") for i in range(len(answers))],
        "chapters": _chapters(groups),
    }


def _pattern(pattern: Pattern, beat: _Beats) -> Json:
    def at(kind: str, ref: str) -> Json:
        return _locator(pattern, kind, ref)

    cues = [at("cue", f"cues[{i}]") for i in range(len(pattern.cues))]
    opening = [beat("cue", chunk, "when this pattern applies") for chunk in _chunks(cues)]
    method: list[Json] = []
    for i, step in enumerate(pattern.workflow):
        method.append(
            beat(
                "step",
                [at("workflow", f"workflow[{i}]")],
                f"step {i + 1} and what it applies",
                shown=1,
            )
        )
        method.extend(
            beat(
                "case",
                [at("case", f"workflow[{i}].cases[{j}]")],
                f"case {j + 1} of step {i + 1}",
                shown=1,
            )
            for j in range(len(step.cases))
        )
    worked = [
        beat(
            "example",
            [at("example", "examples[0]"), at("workflow", f"workflow[{i}]")],
            f"step {i + 1} of the worked example",
            shown=1,
        )
        for i in range(len(pattern.workflow))
    ]
    groups: list[tuple[str, list[Json], Json]] = [
        ("When it applies", opening, {}),
        ("The method", method, {}),
        ("Worked example", worked, {}),
    ]
    if pattern.pitfalls:
        groups.append(
            (
                "Pitfalls",
                [
                    beat(
                        "pitfall",
                        [at("pitfall", f"pitfalls[{i}]")],
                        f"pitfall {i + 1}: wrong, then right",
                        shown=2,
                    )
                    for i in range(len(pattern.pitfalls))
                ],
                {},
            )
        )
    closing = [at("marking", "marking")] if pattern.marking else []
    closing += [at("variation", f"variations[{i}]") for i in range(len(pattern.variations))]
    groups.append(
        (
            "Recap",
            [
                beat("recap", chunk, "the steps in order")
                for chunk in _chunks(closing or [at("workflow", "workflow[0]")])
            ],
            {},
        )
    )
    left = [
        {
            "locator": at("example", f"examples[{i}]"),
            "reason": f"{PLACEHOLDER} repeats case N, or work it in its own chapter",
        }
        for i in range(1, len(pattern.examples))
    ]
    return {
        "pattern": pattern.key,
        "pattern_hash": teaching_hash(pattern),
        "chapters": _chapters(groups),
        "left_to_page": left,
    }


def video(root: Path, stem: str, language: str = "en") -> dict[str, JsonValue]:
    from tum_mcp.course.media.video_content import StoryboardFile
    from tum_mcp.course.media.video_project import _planned, videos
    from tum_mcp.course.media.video_sources import read_sources

    path = videos(root, f"storyboards/{stem}.json")
    if path.exists():
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"videos/storyboards/{stem}.json exists; an outline is only a new draft.",
        )
    source = read_sources(root).get(_planned(root, stem))
    beat = _Beats()
    match source.data:
        case Unit() as unit:
            body = _unit(unit, beat)
        case Exercise() as exercise:
            body = _exercise(exercise, source.exercise.set if source.exercise else "", beat)
        case Pattern() as pattern:
            body = _pattern(pattern, beat)
    board = {"video": stem, "title": str(source.data.title)[:150], "language": language, **body}
    StoryboardFile.model_validate(board)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "storyboard": f"videos/storyboards/{stem}.json",
        "beats": beat.count,
        "to_write": len(unwritten(board)),
    }


def _source(value: str) -> tuple[str, str, str | None]:
    kind, _, key = value.partition(":")
    group, _, key = key.rpartition("/") if kind == "exercise" else ("", "", key)
    if kind not in {"unit", "exercise", "pattern", "concept"} or not key:
        raise CampusError(
            Code.INVALID_RESPONSE,
            "Name sources as unit:KEY, exercise:SET/KEY, pattern:KEY or concept:KEY.",
        )
    return kind, key, group or None


def audio(
    root: Path, stem: str, sources: list[str], title: str | None = None
) -> dict[str, JsonValue]:
    from tum_mcp.course.media.audio_project import CategoryScript, _documents
    from tum_mcp.course.media.audio_project import audio as folder

    path = folder(root, f"categories/{stem}.json")
    if path.exists():
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"audio/categories/{stem}.json exists; an outline is only a new draft.",
        )
    study, exam, exercises = _documents(root)
    units: list[Json] = []
    chapters: list[Json] = []
    first_title = ""
    for value in sources:
        kind, key, group = _source(value)
        item = find(study, exercises, exam, kind, key, group)
        if item is None:
            raise CampusError(Code.STALE_RESULT, f"'{value}' is not a prepared source.")
        first_title = first_title or str(item.title)
        ref: Json = {"kind": kind, "unit": key, **({"set": group} if group else {})}
        units.append(ref)
        covers = [ref | {"locator": _locator(item, k, r)} for k, r in required_parts(item)]
        for n, chunk in enumerate(_chunks(covers, 200), 1):
            chapters.append(
                {
                    "key": f"{key}-{n}"[:100] if len(covers) > 200 else key,
                    "title": str(item.title)[:150],
                    "covers": chunk,
                    "sentences": [
                        f"{PLACEHOLDER} open by naming {item.title}, then say each part."
                    ],
                }
            )
    voices = folder(root, "voice.json")
    profiles = (
        json.loads(voices.read_text(encoding="utf-8")).get("profiles", {})
        if voices.is_file()
        else {}
    )
    script = {
        "key": stem.split("_", 1)[-1],
        "stem": stem,
        "title": (title or first_title)[:150],
        "voice": next(iter(profiles), "narrator"),
        "units": units,
        "chapters": chapters,
    }
    CategoryScript.model_validate(script)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(script, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "script": f"audio/categories/{stem}.json",
        "chapters": len(chapters),
        "to_write": len(unwritten(script)),
    }
