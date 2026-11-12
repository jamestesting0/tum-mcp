"""Read Exam content, derive every statistic in code, and project it for the app."""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from pydantic import JsonValue, ValidationError

from tum_mcp.course.checks.report import (
    PARAGRAPH_SENTENCES,
    PARAGRAPH_WORDS,
    _sentences,
    echoed_meanings,
    generic_meanings,
    math_word_flag,
    math_words,
    plain_math,
    redeclared_meanings,
    renamed_meanings,
    slash_quotients,
    typed_math_labels,
    unexplained_variables,
    visual_state_flags,
)
from tum_mcp.course.content.exam import (
    CONSIDERED,
    NEAR_VERBATIM,
    ExamContent,
    Mock,
    block_text,
    concept_revision,
    mock_revision,
    pattern_revision,
    shingles,
    similarity,
    variant_revision,
)
from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.latex import inline_math
from tum_mcp.course.content.store import locate, read_json
from tum_mcp.course.content.study import StudyContent, compile_formulas, has_visual
from tum_mcp.course.project.models import StudyState
from tum_mcp.course.project.store import confined, digest
from tum_mcp.errors import CampusError, Code

# Ordering weights (sitting occurrence, points share, recent occurrence); missing parts
# are dropped and the rest renormalized. The order guides study; it is not a probability.
WEIGHTS = {"sittings": 0.6, "points": 0.25, "recent": 0.15}
RECENT = 3
# Flexible targets (decision D11): reported for the agent to judge, never enforced.
TARGETS = {
    "concept_line": 240,
    "workflow_steps": 8,
    "cues": 6,
    "map_nodes": 80,
    "mock_minutes_tolerance": 0.15,
    "scale_share": 0.2,
    "similar_statement": 0.5,
    "topic_share_gap": 0.15,
}


def read_exam(root: Path) -> ExamContent | None:
    body = read_json(root, "exam")
    if body is None:
        return None
    try:
        return ExamContent.model_validate_json(body)
    except ValidationError as error:
        document = json.loads(body)
        problems = [
            locate("exam", document, item["loc"]) + ": " + item["msg"].removeprefix("Value error, ")
            for item in error.errors(include_input=False)
        ]
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid Exam content: " + "; ".join(problems[:5])
        ) from None


def stale_exam(root: Path, state: StudyState, content: ExamContent) -> tuple[str, ...]:
    """Items whose cited sources changed; only these need review before the next build."""
    if state.course.key != content.course_key:
        raise CampusError(Code.SCOPE_DENIED, "Exam belongs to a different course.")
    resources = {item.resource.key: item for item in state.resources}
    current: dict[tuple[str, str], bool] = {}

    def fresh(key: str, sha256: str) -> bool:
        if (key, sha256) not in current:
            stored = resources.get(key)
            relative = stored.path if stored else None
            path = confined(root, relative) if relative else None
            current[(key, sha256)] = bool(
                stored
                and stored.status == "current"
                and stored.sha256 == sha256
                and path is not None
                and path.is_file()
                and digest(path.read_bytes()) == sha256
            )
        return current[(key, sha256)]

    stale: list[str] = []
    if content.profile and not all(fresh(s.key, s.sha256) for s in content.profile.sources):
        stale.append("profile")
    for label, items in (
        ("concept", content.concepts),
        ("pattern", content.patterns),
        ("mock", content.mocks),
    ):
        stale.extend(
            f"{label}:{item.key}"
            for item in items
            if not all(fresh(source.key, source.sha256) for source in item.sources)
        )
    stale.extend(
        f"variant:{variant.key}"
        for sitting in content.sittings
        for variant in sitting.variants
        if not all(fresh(source.key, source.sha256) for source in variant.sources)
    )
    return tuple(stale)


def check_exercise_links(content: ExamContent, exercises: ExerciseContent | None) -> None:
    available = {
        (group.key, exercise.key)
        for group in (exercises.sets if exercises else ())
        for exercise in group.exercises
    }
    for concept in content.concepts:
        for link in concept.exercises:
            if (link.set, link.exercise) not in available:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Cheatsheet entry {concept.key} links to an unprepared exercise: "
                    f"{link.set}/{link.exercise}.",
                )


def check_unit_links(content: ExamContent, study: StudyContent | None) -> None:
    if study is None:
        return
    units = {unit.key for unit in study.units}
    linked = {
        *(key for topic in content.topics for key in topic.units),
        *(key for concept in content.concepts for key in concept.units),
        *(
            prerequisite.unit
            for _, _, question in content.past_questions().values()
            if question.guidance
            for prerequisite in question.guidance.prerequisites
        ),
    }
    missing = sorted(linked - units)
    if missing:
        raise CampusError(
            Code.INVALID_RESPONSE, "Exam links to unknown Study topics: " + ", ".join(missing)
        )
    blocks = {unit.key: {block.key for block in unit.blocks if block.key} for unit in study.units}
    links = [
        *(
            prerequisite
            for _, _, question in content.past_questions().values()
            for prerequisite in (question.guidance.prerequisites if question.guidance else ())
        ),
        *(passage for concept in content.concepts for passage in concept.passages),
    ]
    for link in links:
        if link.block and link.block not in blocks[link.unit]:
            raise CampusError(
                Code.INVALID_RESPONSE,
                f"Exam links to block {link.block}, which unit {link.unit} does not have.",
            )
    from tum_mcp.course.content.exercise_data import check_terms

    check_terms(content.model_dump(mode="json"), study, "Exam")


def _considered(content: ExamContent):
    return [sitting for sitting in content.sittings if sitting.relevance in CONSIDERED]


def exam_statistics(content: ExamContent) -> dict[str, JsonValue]:
    """Counts by sitting (one exam) and by variant (Group A/B); outdated sittings excluded."""
    sittings = sorted(_considered(content), key=lambda item: (item.held, item.key))
    recent = {item.key for item in sittings[-RECENT:]}
    variants = [(sitting, variant) for sitting in sittings for variant in sitting.variants]
    classified = [
        question
        for _, variant in variants
        for question in variant.questions
        if question.status == "classified"
    ]
    marked = bool(classified) and all(question.points is not None for question in classified)
    total_points = sum(question.points or 0 for question in classified) if marked else 0
    patterns: dict[str, dict[str, JsonValue]] = {}
    for pattern in content.patterns:
        seen_sittings, seen_variants, points = set(), 0, 0.0
        for sitting, variant in variants:
            members = [
                question
                for question in variant.questions
                if question.status == "classified" and pattern.key in question.patterns
            ]
            if members:
                seen_sittings.add(sitting.key)
                seen_variants += 1
                points += sum(
                    question.points or 0
                    for question in members
                    if question.patterns[0] == pattern.key
                )
        instances = [
            {
                "question": question.key,
                "sitting": sitting.key,
                "paper": variant.key,
                "label": sitting.label,
                "variant": variant.label,
                "number": question.number,
                "points": question.points,
                "considered": sitting.relevance in CONSIDERED,
                "stored": bool(question.statement),
            }
            for sitting in content.sittings
            for variant in sitting.variants
            for question in variant.questions
            if pattern.key in question.patterns
        ]
        held = [item.held for item in sittings if item.key in seen_sittings]
        components = {
            "sittings": len(seen_sittings) / len(sittings) if sittings else None,
            "points": points / total_points if marked and total_points else None,
            "recent": len(seen_sittings & recent) / len(recent) if recent else None,
        }
        available = {name: value for name, value in components.items() if value is not None}
        weight = sum(WEIGHTS[name] for name in available)
        score = (
            sum(WEIGHTS[name] * value for name, value in available.items()) / weight
            if weight
            else 0
        )
        patterns[pattern.key] = {
            "sittings_seen": len(seen_sittings),
            "sittings_considered": len(sittings),
            "variants_seen": seen_variants,
            "variants_considered": len(variants),
            "last_seen": max(held) if held else None,
            "last_label": next(
                (item.label for item in reversed(sittings) if item.key in seen_sittings), None
            ),
            "points_share": round(components["points"], 4)
            if components["points"] is not None
            else None,
            "score": round(score, 6),
            "instances": instances,
        }
    order = sorted(patterns, key=lambda key: (-float(patterns[key]["score"]), key))
    for rank, key in enumerate(order, 1):
        patterns[key]["rank"] = rank
    coverage = content.concept_coverage()
    return {
        "sittings_considered": len(sittings),
        "sittings_outdated": sum(item.relevance == "outdated" for item in content.sittings),
        "years": [sittings[0].held[:4], sittings[-1].held[:4]] if sittings else [],
        "points_known": marked,
        "patterns": patterns,
        "pattern_order": order,
        "concepts": {
            concept.key: {"sittings_seen": len(coverage.get(concept.key, ()))}
            for concept in content.concepts
        },
        "topic_shares": topic_shares(content, sittings),
    }


def topic_shares(content: ExamContent, sittings=None) -> dict[str, JsonValue]:
    """Mean share of each topic per considered variant, by points when every mark is known."""
    sittings = _considered(content) if sittings is None else sittings
    topic_of = {pattern.key: pattern.topic for pattern in content.patterns}
    variants = [variant for sitting in sittings for variant in sitting.variants]
    by_points = bool(variants) and all(
        question.points is not None
        for variant in variants
        for question in variant.questions
        if question.status == "classified"
    )
    shares: dict[str, float] = defaultdict(float)
    for variant in variants:
        counted = [question for question in variant.questions if question.status == "classified"]
        weights = [question.points if by_points else 1 for question in counted]
        total = sum(weights)
        for question, weight in zip(counted, weights, strict=True):
            if total:
                shares[topic_of[question.patterns[0]]] += weight / total / len(variants)
    return {
        "basis": "points" if by_points else "questions",
        "shares": {key: round(value, 4) for key, value in sorted(shares.items())},
    }


def _mock_topic_shares(content: ExamContent, mock: Mock) -> dict[str, float]:
    topic_of = {pattern.key: pattern.topic for pattern in content.patterns}
    concept_topic = {concept.key: concept.topic for concept in content.concepts}
    shares: dict[str, float] = defaultdict(float)
    for question in mock.questions:
        topic = (
            topic_of[question.patterns[0]]
            if question.patterns
            else concept_topic[question.concepts[0]]
        )
        shares[topic] += question.points / mock.points
    return {key: round(value, 4) for key, value in sorted(shares.items())}


# Cheatsheet targets that a review must fix or keep with a reason, by report measure.
SHEET_FLAGS = {
    "procedure entry without steps": "method_without_steps",
    "meanings that only rename": "renamed_meaning",
    "meanings that say only 'given'": "generic_meaning",
    "line characters": "long_line",
    "plain mathematics": "sheet_plain_math",
    "displayed quotient with a slash": "slash_quotient",
    "line repeats the formula": "line_repeats_formula",
    "dense paragraph": "sheet_dense_paragraph",
    "variable meanings written as prose": "prose_legend",
}
# "\(b\): maximum branching, \(d\): ..." spells out a meaning list in a sentence.
PROSE_LEGEND = re.compile(r"(?:\\\([^()]{1,30}?\\\)|\b[A-Za-z]\b)\s*:\s+[a-z]")
# A workflow line that computes a value ("Compute the expected utility", "normalize by the
# sum"); a check, choice or report of a result is not a computation.
COMPUTING = re.compile(
    r"\b(?:comput|calculat|multipl|sums?\b|add up|averag|normali[sz]|weight|estimat|"
    r"marginali[sz]|divid)",
    re.IGNORECASE,
)
NOT_COMPUTING = re.compile(
    r"^\s*(?:check|verify|confirm|state|identify|choose|select|stop|report|interpret|decide|name)\b",
    re.IGNORECASE,
)
# An inline formula in an apply text: an equation, sum, fraction or product in LaTeX.
INLINE_FORMULA = re.compile(r"\\\((?:(?!\\\)).)*?(?:=|\\sum|\\frac|\\prod|\\cdot|\\times)", re.S)


def _unformulated(workflow: list[dict]) -> list[str]:
    """Workflow lines that compute a value but show no formula or code to compute it with."""
    lines = [
        (line, apply or {})
        for step in workflow
        for line, apply in (
            (step["do"], step.get("apply")),
            *((case["then"], case.get("apply")) for case in step.get("cases") or ()),
        )
    ]
    return [
        line
        for line, apply in lines
        if COMPUTING.search(line)
        and not NOT_COMPUTING.search(line)
        and not (apply.get("math") or apply.get("code"))
        and not INLINE_FORMULA.search(apply.get("text") or "")
    ]


def _map_flags(content: ExamContent) -> list[dict[str, JsonValue]]:
    """Every cheatsheet has a semester map: each idea on it shows what it builds on, leads to
    or is confused with. An idea with no link worth drawing leaves the map (`on_map: false`)."""
    on_map = [concept.key for concept in content.concepts if concept.on_map]
    if len(content.concepts) < 2:
        return []
    if not on_map:
        detail = "No idea is on the semester map; put the core ideas on it and link them."
    else:
        linked = {key for link in content.links for key in (link.start, link.end)}
        isolated = [key for key in on_map if key not in linked]
        if not isolated:
            return []
        detail = (
            f"{len(isolated)} of {len(on_map)} ideas on the semester map have no link, such as "
            f"{', '.join(isolated[:4])}. Link each to what it builds on (`requires`, `derives`) "
            "or is confused with (`contrasts`), or set `on_map: false` for supporting detail."
        )
    return [{"item": "exam/sheet", "flag": "unlinked_map", "detail": detail}]


def exam_item_flags(content: ExamContent | None) -> list[dict[str, JsonValue]]:
    """Plain-typed mathematics in patterns, past-question help and mocks, and workflows
    that never show the formula, rule or code a step applies."""
    if content is None:
        return []
    texts: dict[str, list[str]] = {}
    for pattern in content.patterns:
        texts[f"exam/pattern/{pattern.key}"] = plain_math(pattern.model_dump(mode="json"))
    for _, _, question in content.past_questions().values():
        if question.patterns:
            texts.setdefault(f"exam/pattern/{question.patterns[0]}", []).extend(
                plain_math(question.model_dump(mode="json"))
            )
    for mock in content.mocks:
        for question in mock.questions:
            key = f"exam/mock/{mock.key}/{question.key}"
            texts[key] = plain_math(question.model_dump(mode="json"))
    worded: dict[str, list[str]] = {}
    for pattern in content.patterns:
        worded[f"exam/pattern/{pattern.key}"] = math_words(pattern.model_dump(mode="json"))
    for _, _, question in content.past_questions().values():
        if question.patterns:
            worded.setdefault(f"exam/pattern/{question.patterns[0]}", []).extend(
                math_words(question.model_dump(mode="json"))
            )
    for mock in content.mocks:
        for question in mock.questions:
            worded[f"exam/mock/{mock.key}/{question.key}"] = math_words(
                question.model_dump(mode="json")
            )
    bare = [
        {
            "item": f"exam/pattern/{pattern.key}",
            "flag": "bare_workflow",
            "detail": "No workflow step or case shows what it applies; give the formula, rule "
            "or code each computing step uses under `apply`.",
        }
        for pattern in content.patterns
        if pattern.workflow
        and not any(
            step.get("apply") or any(case.get("apply") for case in step.get("cases") or ())
            for step in pattern.model_dump(mode="json")["workflow"]
        )
    ]
    bare += [
        {
            "item": f"exam/pattern/{pattern.key}",
            "flag": "bare_workflow",
            "detail": f"{len(lines)} step(s) compute a value without showing the formula, such "
            f"as '{lines[0][:80]}'. Put the formula under `apply`: `math` with its `symbols`, or "
            r"inline in `text` (\(EU(a) = \sum_s P(s \mid a)\,U(s)\)); words such as "
            "'multiply and sum' are not a formula.",
        }
        for pattern in content.patterns
        if pattern.workflow
        and f"exam/pattern/{pattern.key}" not in {flag["item"] for flag in bare}
        and (lines := _unformulated(pattern.model_dump(mode="json")["workflow"]))
    ]
    bare += [math_word_flag(item, words) for item, words in worded.items() if words]
    bare += _map_flags(content)
    return bare + [
        {
            "item": item,
            "flag": "plain_math",
            "detail": f"{len(found)} text(s) type mathematics as plain characters, such as "
            f"'{found[0]}'. Write every symbol, variable and formula as inline LaTeX.",
        }
        for item, found in texts.items()
        if found
    ]


def sheet_flags(content: ExamContent | None) -> list[dict[str, JsonValue]]:
    """The cheatsheet's report targets as review prompts on the cheatsheet item."""
    if content is None:
        return []
    return [
        {"item": target["item"], "flag": SHEET_FLAGS[measure], "detail": target["value"]}
        for target in exam_report(content)["targets"]
        if str(target["item"]).startswith("concept:")
        and (measure := str(target["measure"])) in SHEET_FLAGS
    ] + [
        flag
        for concept in content.concepts
        for flag in visual_state_flags(f"concept:{concept.key}", concept.model_dump(mode="json"))
    ]


RETRIEVED_KINDS = frozenset({"definition", "fact", "theorem", "formula"})


def retrieval_flags(
    exam: ExamContent | None, study: StudyContent | None
) -> list[dict[str, JsonValue]]:
    """Check retrieval in prepared Study passages linked to an entry, within that scope."""
    if exam is None or study is None:
        return []
    asked: dict[str, str] = {
        unit.key: " ".join(
            [card.front + " " + card.back for card in unit.flashcards]
            + [
                " ".join(
                    [question.prompt, question.explanation, *(o.text for o in question.options)]
                )
                for question in unit.questions
            ]
        ).casefold()
        for unit in study.units
    }
    flags: list[dict[str, JsonValue]] = []
    for concept in exam.concepts:
        if concept.kind not in RETRIEVED_KINDS:
            continue
        units = {*concept.units, *(passage.unit for passage in concept.passages)}
        if not units:
            continue
        if not any(concept.title.casefold() in asked.get(unit, "") for unit in units):
            flags.append(
                {
                    "item": f"concept:{concept.key}",
                    "flag": "unretrieved_entry",
                    "detail": f"No Study flashcard or question asks for '{concept.title}'.",
                }
            )
    return flags


def practice_flags(content: ExamContent | None) -> list[dict[str, JsonValue]]:
    """Prepared practice keeps its optional guidance and visual state usable."""
    if content is None:
        return []

    def line_identity(text: str) -> str:
        return " ".join(text.lower().split()).rstrip(".;:!?")

    flags: list[dict[str, JsonValue]] = []
    for mock in content.mocks:
        for question in mock.questions:
            flags.extend(
                visual_state_flags(
                    f"exam/mock/{mock.key}/{question.key}", question.model_dump(mode="json")
                )
            )
    for pattern in content.patterns:
        for number, step in enumerate(pattern.workflow, 1):
            applications = [
                (f"step {number}", step.do, step.apply),
                *(
                    (f"step {number}, case {index}", case.then, case.apply)
                    for index, case in enumerate(step.cases, 1)
                ),
            ]
            for location, summary, applied in applications:
                if (
                    applied
                    and applied.text
                    and not (applied.math or applied.code)
                    and line_identity(applied.text) == line_identity(summary)
                ):
                    flags.append(
                        {
                            "item": f"exam/pattern/{pattern.key}",
                            "flag": "redundant_workflow_detail",
                            "detail": f"Workflow {location} expands to its own summary. "
                            "Omit apply when the one-line rule is complete, or add the "
                            "missing formula, code, condition or useful working detail.",
                        }
                    )
        flags.extend(
            visual_state_flags(f"exam/pattern/{pattern.key}", pattern.model_dump(mode="json"))
        )
        for item in pattern.drill:
            if not item.guide:
                flags.append(
                    {
                        "item": f"exam/pattern/{pattern.key}",
                        "flag": "unguided_practice",
                        "detail": f"Practice '{item.key}' has a solution but no optional guide. "
                        "Prepare staged prompts, hints and explained answers in guide; "
                        "keep help hidden for the initial attempt.",
                    }
                )
        for sitting, _, question in content.past_questions().values():
            if (
                sitting.relevance in CONSIDERED
                and question.status == "classified"
                and pattern.key in question.patterns
            ):
                flags.extend(
                    visual_state_flags(
                        f"exam/pattern/{pattern.key}", question.model_dump(mode="json")
                    )
                )
                if question.guidance is None:
                    flags.append(
                        {
                            "item": f"exam/pattern/{pattern.key}",
                            "flag": "unguided_practice",
                            "detail": f"Past question '{question.key}' has no prepared guidance. "
                            "Write task-specific guidance.steps with prompts, hints and explained "
                            "checks; a generic solve-the-question step is not a guide.",
                        }
                    )
    return flags


def meta_flags(content: ExamContent | None) -> list[dict[str, JsonValue]]:
    """Bookkeeping in the exam and variant labels a pattern page shows."""
    from tum_mcp.course.checks.report import META_REFERENCE, PROVENANCE

    if content is None:
        return []
    flags: list[dict[str, JsonValue]] = []
    for pattern in content.patterns:
        labels = sorted(
            {
                label
                for sitting in content.sittings
                for variant in sitting.variants
                if any(pattern.key in question.patterns for question in variant.questions)
                for label in (sitting.label, variant.label)
                if PROVENANCE.search(label) or META_REFERENCE.search(label)
            }
        )
        if labels:
            flags.append(
                {
                    "item": f"exam/pattern/{pattern.key}",
                    "flag": "meta_reference",
                    "detail": f"The exam label '{labels[0]}' carries bookkeeping; name the exam "
                    "only and keep where it came from in the ledger.",
                }
            )
    return flags


def exam_report(content: ExamContent) -> dict[str, JsonValue]:
    """What an agent needs before writing forecasts or reviewing: blueprint, risks, targets."""
    statistics = exam_statistics(content)
    history = statistics["topic_shares"]["shares"]
    past = {
        key: shingles(block_text(question.statement))
        for key, (_, _, question) in content.past_questions().items()
        if question.statement
    }
    drilled = {
        concept for pattern in content.patterns if pattern.drill for concept in pattern.concepts
    }
    in_mocks = {concept for mock in content.mocks for q in mock.questions for concept in q.concepts}
    targets: list[dict[str, JsonValue]] = []

    def flag(item: str, measure: str, value: JsonValue, target: JsonValue) -> None:
        targets.append({"item": item, "measure": measure, "value": value, "target": target})

    for concept in content.concepts:
        # A one-line fact is complete as it is; a method needs its steps, as details or as the
        # workflow of the pattern it names.
        if concept.kind in {"procedure", "algorithm"} and not (
            concept.details or concept.workflow_from
        ):
            flag(f"concept:{concept.key}", "procedure entry without steps", concept.kind, [])
        if renamed := renamed_meanings(concept.model_dump(mode="json")):
            flag(f"concept:{concept.key}", "meanings that only rename", renamed[:5], [])
        # The formula's spoken reading is plain words by design.
        if typed := plain_math(concept.model_dump(mode="json", exclude={"formula": {"plain"}})):
            flag(f"concept:{concept.key}", "plain mathematics", typed[:5], [])
        if concept.formula and "".join(concept.formula.latex.split()) in {
            "".join(span.split()).rstrip(".,;") for span in inline_math(concept.line)
        }:
            flag(f"concept:{concept.key}", "line repeats the formula", concept.line[:120], [])
        # Paragraphs and points, and the captions and descriptions under tables and drawings.
        texts: list[str] = []
        for block in concept.details:
            texts += [*getattr(block, "paragraphs", ()), *getattr(block, "points", ())]
            for name in ("caption", "description", "explanation"):
                if isinstance(text := getattr(block, name, None), str):
                    texts.append(text)
        if dense := [
            text[:80]
            for text in texts
            if len(text.split()) > PARAGRAPH_WORDS or _sentences(text) > PARAGRAPH_SENTENCES
        ]:
            flag(f"concept:{concept.key}", "dense paragraph", dense[:3], [])
        if legends := [
            text[:80] for text in (concept.line, *texts) if len(PROSE_LEGEND.findall(text)) >= 2
        ]:
            flag(f"concept:{concept.key}", "variable meanings written as prose", legends[:3], [])
        if concept.formula and (slashes := slash_quotients(concept.formula.latex)):
            flag(f"concept:{concept.key}", "displayed quotient with a slash", slashes[:5], [])
        if generic := generic_meanings(concept.model_dump(mode="json")):
            flag(f"concept:{concept.key}", "meanings that say only 'given'", generic[:5], [])
        if len(concept.line) > TARGETS["concept_line"]:
            flag(
                f"concept:{concept.key}",
                "line characters",
                len(concept.line),
                TARGETS["concept_line"],
            )
    on_map = sum(concept.on_map for concept in content.concepts)
    if on_map > TARGETS["map_nodes"]:
        flag("map", "concepts on the map", on_map, TARGETS["map_nodes"])
    for pattern in content.patterns:
        if len(pattern.workflow) > TARGETS["workflow_steps"]:
            flag(
                f"pattern:{pattern.key}",
                "workflow steps",
                len(pattern.workflow),
                TARGETS["workflow_steps"],
            )
        if len(pattern.cues) > TARGETS["cues"]:
            flag(f"pattern:{pattern.key}", "cues", len(pattern.cues), TARGETS["cues"])
        value = pattern.model_dump(mode="json")
        if missing := unexplained_variables(value, task=True):
            flag(f"pattern:{pattern.key}", "variables without a meaning", missing[:5], [])
        if generic := generic_meanings(value):
            flag(f"pattern:{pattern.key}", "meanings that say only 'given'", generic[:5], [])
        if typed := typed_math_labels(value):
            flag(f"pattern:{pattern.key}", "figure labels typing math", typed[:5], [])
        if renamed := renamed_meanings(value):
            flag(f"pattern:{pattern.key}", "meanings that only rename", renamed[:5], [])
        if repeated := redeclared_meanings(value):
            flag(f"pattern:{pattern.key}", "meanings declared more than once", repeated[:5], [])
        if echoed := echoed_meanings(value):
            flag(f"pattern:{pattern.key}", "meanings repeated beside the formula", echoed[:5], [])
    mocks: list[dict[str, JsonValue]] = []
    profile = content.profile
    for mock in content.mocks:
        minutes = sum(question.minutes for question in mock.questions)
        scale = sum(q.points for q in mock.questions if q.change == "scale") / mock.points
        shares = _mock_topic_shares(content, mock)
        similar = []
        for question in mock.questions:
            own = shingles(block_text(question.statement))
            best = max(
                ((similarity(own, text), key) for key, text in past.items()), default=(0.0, None)
            )
            if best[1] and TARGETS["similar_statement"] <= best[0] < NEAR_VERBATIM:
                similar.append(
                    {"question": question.key, "past": best[1], "similarity": round(best[0], 3)}
                )
                flag(
                    f"mock:{mock.key}/{question.key}",
                    "similarity to a past statement",
                    round(best[0], 3),
                    TARGETS["similar_statement"],
                )
        if (
            abs(minutes - mock.duration_minutes)
            > TARGETS["mock_minutes_tolerance"] * mock.duration_minutes
        ):
            flag(
                f"mock:{mock.key}", "estimated minutes vs duration", minutes, mock.duration_minutes
            )
        if (
            profile
            and profile.duration_minutes
            and mock.duration_minutes != profile.duration_minutes
        ):
            flag(
                f"mock:{mock.key}",
                "duration vs the real exam",
                mock.duration_minutes,
                profile.duration_minutes,
            )
        if profile and profile.total_points and abs(mock.points - profile.total_points) > 1e-6:
            flag(f"mock:{mock.key}", "points vs the real exam", mock.points, profile.total_points)
        if scale > TARGETS["scale_share"]:
            flag(
                f"mock:{mock.key}",
                "share of numbers-only variants",
                round(scale, 3),
                TARGETS["scale_share"],
            )
        for topic in sorted(set(history) | set(shares)):
            gap = abs(shares.get(topic, 0) - history.get(topic, 0))
            if history and gap > TARGETS["topic_share_gap"]:
                flag(
                    f"mock:{mock.key}",
                    f"topic share gap ({topic})",
                    round(gap, 3),
                    TARGETS["topic_share_gap"],
                )
        mocks.append(
            {
                "key": mock.key,
                "points": mock.points,
                "minutes": minutes,
                "duration_minutes": mock.duration_minutes,
                "topic_shares": shares,
                "formats": dict(Counter(question.format for question in mock.questions)),
                "difficulty": dict(
                    Counter(str(question.difficulty) for question in mock.questions)
                ),
                "novelty": dict(Counter(question.novelty for question in mock.questions)),
                "scale_share": round(scale, 3),
                "similar_statements": similar,
            }
        )
    # Printed past questions stay as printed; guided ones should add a picture in a step.
    for key, (_, _, question) in content.past_questions().items():
        guidance = question.guidance.steps if question.guidance else ()
        shown = (*question.statement, *(block for step in guidance for block in step.blocks))
        if question.guidance and not has_visual(shown):
            flag(f"question:{key}", "visual blocks in statement and guidance", 0, 1)
    review = [
        {
            "question": key,
            "sitting": sitting.key,
            "status": question.status,
            "confidence": question.confidence,
            "reason": question.reason,
        }
        for key, (sitting, _, question) in content.past_questions().items()
        if question.status != "classified" or question.confidence == "low"
    ]
    formats = Counter(
        question.format
        for sitting in _considered(content)
        for variant in sitting.variants
        for question in variant.questions
        if question.status == "classified"
    )
    return {
        "statistics": statistics,
        "blueprint": {
            "profile": profile.model_dump(mode="json", exclude={"sources"}) if profile else None,
            "topic_shares": statistics["topic_shares"],
            "formats": dict(formats),
            "mocks": mocks,
        },
        "review": review,
        "uncovered_core": sorted(
            concept.key
            for concept in content.concepts
            if concept.tier == "core" and concept.key not in drilled | in_mocks
        ),
        "targets": targets,
    }


def exam_revisions(content: ExamContent) -> dict[str, str]:
    """Revision of every commentable Exam item, keyed as the app's comment anchors."""
    revisions = {f"concept:{item.key}": concept_revision(item) for item in content.concepts}
    revisions |= {f"pattern:{item.key}": pattern_revision(item) for item in content.patterns}
    revisions |= {f"mock:{item.key}": mock_revision(item) for item in content.mocks}
    for sitting in content.sittings:
        for variant in sitting.variants:
            revision = variant_revision(variant)
            revisions |= {f"question:{question.key}": revision for question in variant.questions}
    return revisions


def render_exam(content: ExamContent) -> dict[str, JsonValue]:
    from tum_mcp.course.content.exam_layout import NARROW, layout

    value = compile_formulas(content.model_dump(mode="json", exclude_none=True))
    for concept, rendered in zip(content.concepts, value.get("concepts", []), strict=True):
        rendered["revision"] = concept_revision(concept)
    for pattern, rendered in zip(content.patterns, value.get("patterns", []), strict=True):
        rendered["revision"] = pattern_revision(pattern)
    for mock, rendered in zip(content.mocks, value.get("mocks", []), strict=True):
        rendered["revision"] = mock_revision(mock)
        rendered["points"] = mock.points
    for sitting, rendered_sitting in zip(content.sittings, value.get("sittings", []), strict=True):
        for variant, rendered in zip(sitting.variants, rendered_sitting["variants"], strict=True):
            rendered["revision"] = variant_revision(variant)
            rendered["replayable"] = variant.replayable
    value["statistics"] = exam_statistics(content)
    wide = layout(content)
    if wide["nodes"]:
        narrow = layout(content, NARROW)
        wide["narrow"] = {key: item for key, item in narrow.items() if key != "overview"}
    value["map"] = wide
    return value
