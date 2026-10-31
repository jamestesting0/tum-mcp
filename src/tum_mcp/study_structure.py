"""The course as a whole: its outline, the links between workspaces and code-found structure flags.

The course review scores organization, redundancy and integration from this map. Code tracks
the outline's revision, so the course review turns stale when units, categories or links change,
not when a passage is reworded.
"""

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from itertools import combinations

from pydantic import JsonValue

from tum_mcp.exam_content import ExamContent
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.lecture_content import LectureContent
from tum_mcp.study_content import Block, DefinitionBlock, StudyContent, TextBlock, term_markers
from tum_mcp.study_coverage import CoverageLedger
from tum_mcp.study_duplicates import similarity, sketch
from tum_mcp.study_report import FLAT_OUTLINE_UNITS

# Shared wording above this share of five-word shingles means one passage repeats the other.
PASSAGE_SIMILARITY = 0.5
# Practice items this close in words ask the same thing in the same form.
PRACTICE_SIMILARITY = 0.8
PRACTICE_WORDS = 6
# A section citing pages this far before an earlier section's pages left the lesson's order.
PAGE_RETURN = 10
FLAT_SECTIONS = 8
CATCH_ALL = re.compile(
    r"^(?:misc(?:ellaneous)?|others?|general|more|extras?|additional(?: topics)?|various|rest)$",
    re.IGNORECASE,
)
WORD = re.compile(r"[^\W_]+")
# Records one flag: the item it points at, its kind and what to change.
Flag = Callable[[str, str, str], None]


def workspaces(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    lectures: LectureContent | None,
) -> list[str]:
    present = {"study": content, "exercises": exercises, "exam": exam, "lectures": lectures}
    return [name for name, value in present.items() if value is not None]


def structure_revision(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    lectures: LectureContent | None,
    *,
    ledger: CoverageLedger | None = None,
) -> str:
    """A hash of what the course review judges: order, categories, homes of terms and links."""
    outline = {
        "study": {
            "organization": content.organization,
            "units": [
                {
                    "key": unit.key,
                    "path": unit.path,
                    "title": unit.title,
                    "headings": _headings(unit.blocks),
                    "defines": sorted(_defined(unit.blocks)),
                    "lectures": unit.lectures,
                    **(
                        {
                            "explore": [
                                (item.key, item.title, [b.key for b in item.blocks])
                                for item in unit.explore
                            ]
                        }
                        if unit.explore
                        else {}
                    ),
                }
                for unit in content.units
            ],
        }
        if content
        else None,
        "exercises": [
            {
                "key": group.key,
                "title": group.title,
                "category": group.category,
                "week": group.week,
                "exercises": [
                    {
                        "key": exercise.key,
                        "title": exercise.title,
                        "headings": _headings(exercise.statement),
                        "part_blocks": exercise.part_blocks,
                        "prerequisites": [(p.unit, p.block) for p in exercise.prerequisites],
                    }
                    for exercise in group.exercises
                ],
            }
            for group in exercises.sets
        ]
        if exercises
        else None,
        "exam": {
            "topics": [(t.key, t.title, t.order, t.units) for t in exam.topics],
            "concepts": [(c.key, c.topic, c.title, c.units) for c in exam.concepts],
            "patterns": [(p.key, p.topic, p.title, p.concepts) for p in exam.patterns],
            "links": [(link.start, link.end, link.kind) for link in exam.links],
        }
        if exam
        else None,
        "lectures": [(lecture.key, lecture.title) for lecture in lectures.lectures]
        if lectures
        else None,
    }
    classifications = (
        [
            (
                entry.source,
                outcome.key,
                outcome.classification.model_dump(mode="json"),
                [(ref.unit, ref.item) for ref in outcome.explore],
            )
            for entry in ledger.sources
            for outcome in entry.outcomes
            if outcome.classification is not None
        ]
        if ledger
        else []
    )
    if classifications:
        outline["enrichment_classification"] = classifications
    payload = json.dumps(outline, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def course_map(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    lectures: LectureContent | None,
    *,
    ledger: CoverageLedger | None = None,
) -> dict[str, JsonValue]:
    """Every workspace in course order with what each unit builds on and what links to it."""
    result: dict[str, JsonValue] = {
        "revision": structure_revision(content, exercises, exam, lectures, ledger=ledger),
        "workspaces": workspaces(content, exercises, exam, lectures),
    }
    if content:
        result["study"] = _study_map(content, exercises, exam)
    if exercises:
        result["exercises"] = [
            {
                "item": f"exercises/{group.key}/{exercise.key}",
                "set": group.title,
                "title": exercise.title,
                "requires": [
                    f"{p.unit}#{p.block}" if p.block else p.unit for p in exercise.prerequisites
                ],
            }
            for group in exercises.sets
            for exercise in group.exercises
        ]
    if exam:
        result["exam"] = {
            "topics": [
                {"key": topic.key, "title": topic.title, "units": list(topic.units)}
                for topic in sorted(exam.topics, key=lambda topic: topic.order)
            ],
            "concepts": len(exam.concepts),
            "patterns": len(exam.patterns),
        }
    if lectures:
        linked = {key for unit in content.units for key in unit.lectures} if content else set()
        result["lectures"] = [
            {"key": lecture.key, "title": lecture.title, "linked": lecture.key in linked}
            for lecture in lectures.lectures
        ]
    result["flags"] = structure_flags(content, exercises, exam, lectures)
    return result


def _study_map(
    content: StudyContent, exercises: ExerciseContent | None, exam: ExamContent | None
) -> dict[str, JsonValue]:
    required: dict[str, list[str]] = defaultdict(list)
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            for unit in dict.fromkeys(p.unit for p in exercise.prerequisites):
                required[unit].append(f"exercises/{group.key}/{exercise.key}")
    cited: dict[str, list[str]] = defaultdict(list)
    for concept in exam.concepts if exam else ():
        for unit in concept.units:
            cited[unit].append(concept.key)
    homes = _homes(content)
    units: list[JsonValue] = []
    for unit in content.units:
        used = sorted(term_markers(unit.model_dump(mode="json", exclude={"explore"})))
        builds_on = list(
            dict.fromkeys(homes[t] for t in used if homes.get(t, unit.key) != unit.key)
        )
        units.append(
            {
                "item": f"study/{unit.key}",
                "title": unit.title,
                "path": list(unit.path),
                "sections": sum(1 for block in unit.blocks if block.title),
                "headings": _headings(unit.blocks),
                "defines": sorted(_defined(unit.blocks)),
                **(
                    {
                        "explore": [
                            {
                                "key": item.key,
                                "title": item.title,
                                "sources": [source.key for source in item.sources],
                            }
                            for item in unit.explore
                        ]
                    }
                    if unit.explore
                    else {}
                ),
                **({"builds_on": builds_on} if builds_on else {}),
                **({"lectures": list(unit.lectures)} if unit.lectures else {}),
                **({"exercises": required[unit.key]} if required[unit.key] else {}),
                **({"exam_concepts": cited[unit.key]} if cited[unit.key] else {}),
            }
        )
    return {"organization": content.organization, "units": units}


def structure_flags(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    lectures: LectureContent | None,
) -> list[dict[str, JsonValue]]:
    """Measurable signs of a hard-to-follow, repetitive or disconnected course; each is a prompt
    to review, not a rule."""
    flags: list[dict[str, JsonValue]] = []

    def flag(item: str, kind: str, detail: str) -> None:
        flags.append({"item": item, "flag": kind, "detail": detail})

    if content:
        _forward_terms(content, flag)
        _source_order(content, flag)
        for unit in content.units:
            headings = _headings(unit.blocks)
            if len(headings) >= FLAT_SECTIONS and all(h["level"] == 1 for h in headings):
                flag(
                    f"study/{unit.key}",
                    "flat_sections",
                    f"{len(headings)} headings are all level 1; review whether examples, cases "
                    "or supporting arguments belong under their parent topics. Keep genuinely "
                    "parallel topics as peers; do not add headings just to use every level.",
                )
        _categories(content, flag)
        _titles(content, exercises, flag)
    _order(content, exercises, exam, flag)
    _passages(content, exercises, exam, flag)
    if content:
        _practice(content, flag)
        _links(content, exercises, exam, lectures, flag)
    return flags


def _defined(blocks: tuple[Block, ...]) -> set[str]:
    return {block.term.casefold() for block in blocks if isinstance(block, DefinitionBlock)}


def _headings(blocks: tuple[Block, ...]) -> list[dict[str, JsonValue]]:
    return [
        {"title": block.title, "level": block.level}
        for block in blocks
        if block.title and block.kind != "definition"
    ]


def _homes(content: StudyContent) -> dict[str, str]:
    return {term: unit.key for unit in content.units for term in _defined(unit.blocks)}


def _source_order(content: StudyContent, flag: Flag) -> None:
    """Sections that jump back to much earlier pages of the unit's main source, the usual trace of
    a section appended after the lesson was written."""
    for unit in content.units:
        primary, furthest, late = unit.sources[0].key, 0, []
        for block in unit.blocks:
            if not (block.title and block.pages and block.sources and block.sources[0] == primary):
                continue
            first = int(block.pages.split("-")[0])
            if first + PAGE_RETURN < furthest:
                late.append((block.title, block.pages, furthest))
            furthest = max(furthest, first)
        if late:
            title, pages, after = late[0]
            flag(
                f"study/{unit.key}",
                "source_order",
                f"{len(late)} section(s) return to much earlier source pages, such as '{title}' "
                f"(p. {pages}) after sections from p. {after}; move each to where the lesson "
                "teaches its pages, or state why it comes later.",
            )


def _sections(blocks: tuple[Block, ...]) -> list[int]:
    """The section each block shows in: a titled block opens one, and a definition appears
    inside the passage before it, so the passage that introduces a term may already mark it."""
    sections, current = [], 0
    for position, block in enumerate(blocks):
        if position and block.title and not isinstance(block, DefinitionBlock):
            current += 1
        sections.append(current)
    return sections


def _forward_terms(content: StudyContent, flag: Flag) -> None:
    taught = {
        block.term.casefold(): (index, section, unit.title)
        for index, unit in enumerate(content.units)
        for block, section in zip(unit.blocks, _sections(unit.blocks), strict=True)
        if isinstance(block, DefinitionBlock)
    }
    for index, unit in enumerate(content.units):
        early: list[tuple[str, str, str]] = []
        for block, section in zip(unit.blocks, _sections(unit.blocks), strict=True):
            for term in sorted(term_markers(block.model_dump(mode="json"))):
                home = taught.get(term)
                if home and home[:2] > (index, section):
                    where = "a later section of this unit" if home[0] == index else home[2]
                    early.append((term, block.title or block.kind, where))
        # Cards and questions follow the whole lesson, so only a later unit is too late.
        for practice in (*unit.flashcards, *unit.questions):
            for term in sorted(term_markers(practice.model_dump(mode="json"))):
                home = taught.get(term)
                if home and home[0] > index:
                    early.append((term, f"practice {practice.key}", home[2]))
        if early:
            term, where, home = early[0]
            flag(
                f"study/{unit.key}",
                "forward_term",
                f"{len(early)} use(s) of a term before it is taught, such as {{{{{term}}}}} in "
                f"'{where}', taught in '{home}'. Teach it first, or move this part after it.",
            )


def _categories(content: StudyContent, flag: Flag) -> None:
    units = content.units
    sizes: Counter[tuple[str, ...]] = Counter(
        unit.path[:depth] for unit in units for depth in range(1, len(unit.path) + 1)
    )
    children: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for unit in units:
        for depth in range(len(unit.path)):
            children[unit.path[:depth]].add(unit.path[depth])
    # Lecture and week groups follow the calendar, so a short lecture may hold one unit.
    topical = content.organization == "topics"
    for group, size in sizes.items():
        siblings = [(*group[:-1], label) for label in children[group[:-1]] if label != group[-1]]
        if topical and size == 1 and any(sizes[sibling] > 1 for sibling in siblings):
            unit = next(unit for unit in units if unit.path[: len(group)] == group)
            flag(
                f"study/{unit.key}",
                "singleton_category",
                f"'{' / '.join(group)}' holds only this unit beside larger groups; join it to the "
                "group it belongs with.",
            )
        if CATCH_ALL.match(group[-1].strip()):
            flag(
                "outline",
                "catch_all_category",
                f"'{' / '.join(group)}' names no topic; group these units by the lecture, week or "
                "topic they belong to.",
            )
        if children[group] and size < FLAT_OUTLINE_UNITS:
            flag(
                "outline",
                "deep_category",
                f"'{' / '.join(group)}' splits {size} unit(s) into subgroups; a second level helps "
                "only a large group.",
            )
    grouped = [unit for unit in units if unit.path]
    if len(units) > 1 and len(grouped) == len(units) and len(children[()]) == 1:
        flag(
            "outline",
            "deep_category",
            f"Every unit sits in '{grouped[0].path[0]}'; drop the folder that wraps the course.",
        )
    loose = [unit for unit in units if not unit.path]
    if grouped and loose:
        flag(
            "outline",
            "ungrouped_unit",
            f"{len(loose)} unit(s) sit outside every group, such as '{loose[0].title}'; give "
            "each the `path` of its lecture, week or topic.",
        )


def _titles(content: StudyContent, exercises: ExerciseContent | None, flag: Flag) -> None:
    def repeated(titles: list[str]) -> list[str]:
        counts = Counter(title.strip().casefold() for title in titles)
        return [title for title in dict.fromkeys(titles) if counts[title.strip().casefold()] > 1]

    if same := repeated([unit.title for unit in content.units]):
        flag("outline", "duplicate_title", f"Several units are titled '{same[0]}'.")
    for unit in content.units:
        if same := repeated([block.title for block in unit.blocks if block.title]):
            flag(
                f"study/{unit.key}",
                "duplicate_title",
                f"Two sections are titled '{same[0]}'; the Contents list cannot tell them apart.",
            )
    for group in exercises.sets if exercises else ():
        if same := repeated([exercise.title for exercise in group.exercises]):
            flag(
                f"exercises/{group.key}",
                "duplicate_title",
                f"Two exercises are titled '{same[0]}'.",
            )


def _order(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    flag: Flag,
) -> None:
    """Exercise sets and exam topics that run against the order of the units they need."""
    if not content:
        return
    position = {unit.key: index for index, unit in enumerate(content.units)}
    titles = {unit.key: unit.title for unit in content.units}
    sequences: list[tuple[str, list[tuple[str, list[int]]]]] = []
    if exercises:
        sequences.append(
            (
                "exercises",
                [
                    (
                        group.title,
                        [
                            position[p.unit]
                            for exercise in group.exercises
                            for p in exercise.prerequisites
                            if p.unit in position
                        ],
                    )
                    for group in exercises.sets
                ],
            )
        )
    if exam:
        topics = sorted(exam.topics, key=lambda topic: topic.order)
        sequences.append(
            ("exam", [(t.title, [position[u] for u in t.units if u in position]) for t in topics])
        )
    order = list(position)
    for workspace, groups in sequences:
        linked = [(title, needs) for title, needs in groups if needs]
        for (first, before), (second, after) in zip(linked, linked[1:], strict=False):
            if min(before) > max(after):
                flag(
                    workspace,
                    "order_mismatch",
                    f"'{first}' needs '{titles[order[min(before)]]}' and later units, yet the "
                    f"next, '{second}', needs only units up to '{titles[order[max(after)]]}'; "
                    "order Study and this workspace the same way.",
                )


def _text(block: Block) -> str:
    return (
        " ".join((*block.paragraphs, *block.steps, *block.points))
        if isinstance(block, TextBlock)
        else ""
    )


def _passages(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    flag: Flag,
) -> None:
    passages: list[tuple[str, str, str]] = []
    for unit in content.units if content else ():
        passages.extend((f"study/{unit.key}", b.title or "text", _text(b)) for b in unit.blocks)
        for item in unit.explore:
            passages.extend(
                (f"study/{unit.key}/explore/{item.key}", b.title or "text", _text(b))
                for b in item.blocks
            )
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            item = f"exercises/{group.key}/{exercise.key}"
            blocks = (
                *exercise.statement,
                *(block for step in exercise.steps for block in step.blocks),
                *exercise.solution.blocks,
            )
            passages.extend((item, b.title or "text", _text(b)) for b in blocks)
    for concept in exam.concepts if exam else ():
        passages.extend(
            (f"exam/{concept.key}", b.title or concept.title, _text(b)) for b in concept.details
        )
    sketches = [(item, title, s) for item, title, text in passages if (s := sketch(text))]
    shared: Counter[tuple[int, int]] = Counter()
    holders: dict[int, list[int]] = defaultdict(list)
    for index, (_, _, signature) in enumerate(sketches):
        for value in signature:
            holders[value].append(index)
    for indices in holders.values():
        shared.update(combinations(indices, 2))
    for left, right in sorted(shared):
        value = similarity(sketches[left][2], sketches[right][2])
        if value < PASSAGE_SIMILARITY:
            continue
        (first, first_title, _), (second, second_title, _) = sketches[left], sketches[right]
        where = "a later section of this page" if first == second else second
        flag(
            first,
            "near_duplicate_passage",
            f"'{first_title}' and '{second_title}' in {where} share {value:.0%} of their wording; "
            "teach it in one place and link to it from the other.",
        )


def _words(*texts: str) -> frozenset[str]:
    return frozenset(WORD.findall(" ".join(texts).casefold()))


def _practice(content: StudyContent, flag: Flag) -> None:
    """Cards and questions that ask the same thing in nearly the same words; Revision pools them."""
    for kind, items in (
        (
            "question",
            [
                (unit.key, question.key, _words(question.prompt, _correct(question)))
                for unit in content.units
                for question in unit.questions
            ],
        ),
        (
            "card",
            [
                (unit.key, card.key, _words(card.front, card.back))
                for unit in content.units
                for card in unit.flashcards
            ],
        ),
    ):
        # Overlap can reach the threshold only between sets of similar size, so compare each
        # item with the next larger ones and stop once they are too large.
        usable = sorted(
            (
                (order, unit, key, words)
                for order, (unit, key, words) in enumerate(items)
                if len(words) >= PRACTICE_WORDS
            ),
            key=lambda entry: len(entry[3]),
        )
        for index, small in enumerate(usable):
            for large in usable[index + 1 :]:
                if len(small[3]) < PRACTICE_SIMILARITY * len(large[3]):
                    break
                if len(small[3] & large[3]) / len(small[3] | large[3]) < PRACTICE_SIMILARITY:
                    continue
                (_, unit, key, _), (_, other_unit, other, _) = sorted((small, large))
                where = "this unit" if unit == other_unit else f"unit {other_unit}"
                flag(
                    f"study/{unit}",
                    "near_duplicate_practice",
                    f"{kind.capitalize()} {key} and {kind} {other} in {where} ask the same "
                    "thing in nearly the same words; keep one, or change what the student must "
                    "decide.",
                )


def _correct(question) -> str:
    return next(option.text for option in question.options if option.key == question.correct)


def _links(
    content: StudyContent,
    exercises: ExerciseContent | None,
    exam: ExamContent | None,
    lectures: LectureContent | None,
    flag: Flag,
) -> None:
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            item = f"exercises/{group.key}/{exercise.key}"
            if not exercise.prerequisites:
                flag(
                    item,
                    "unlinked_exercise",
                    "Names no Study passage it builds on; add the unit and block a student "
                    "needs, so the passage opens beside the exercise.",
                )
            elif loose := [p.unit for p in exercise.prerequisites if not p.block]:
                flag(
                    item,
                    "unlinked_exercise",
                    f"Links unit {loose[0]} without the block that teaches what the steps use.",
                )
    if exam and (bare := [concept.key for concept in exam.concepts if not concept.units]):
        flag(
            "exam",
            "unlinked_concept",
            f"{len(bare)} cheatsheet concept(s) cite no Study unit, such as {', '.join(bare[:3])}; "
            "link the unit that teaches each.",
        )
    if lectures:
        linked = {key for unit in content.units for key in unit.lectures}
        if bare := [lecture.title for lecture in lectures.lectures if lecture.key not in linked]:
            flag(
                "lectures",
                "unlinked_lecture",
                f"{len(bare)} lecture(s) no unit links, such as '{bare[0]}'; name each in the "
                "`lectures` of the units it teaches.",
            )
