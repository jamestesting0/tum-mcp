"""Read Exam content, derive every statistic in code, and project it for the app."""

from collections import Counter, defaultdict
from pathlib import Path

from pydantic import JsonValue, ValidationError

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.exam_content import (
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
from tum_mcp.study_content import StudyContent, compile_formulas, has_visual
from tum_mcp.study_models import StudyState
from tum_mcp.study_store import confined, digest

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
    path = app_path(root, "exam.json")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise CampusError(Code.INVALID_RESPONSE, "Exam content must be a file below 8 MiB.")
    try:
        return ExamContent.model_validate_json(path.read_bytes())
    except ValidationError as error:
        problems = [
            ".".join(map(str, item["loc"])) + ": " + item["msg"].removeprefix("Value error, ")
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
    for _, _, question in content.past_questions().values():
        for prerequisite in question.guidance.prerequisites if question.guidance else ():
            if prerequisite.block and prerequisite.block not in blocks[prerequisite.unit]:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Exam links to block {prerequisite.block}, which unit "
                    f"{prerequisite.unit} does not have.",
                )
    from tum_mcp.exercise_data import check_terms

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
    from tum_mcp.exam_layout import layout

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
    value["map"] = layout(content)
    return value
