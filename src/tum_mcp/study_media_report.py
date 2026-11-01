"""Evidence-bound media scores, kept separate from the prepared-content averages."""

from collections import Counter
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.errors import CampusError, Code
from tum_mcp.media_projection import file_hash
from tum_mcp.study_media import MediaInventory, MediaItem
from tum_mcp.study_review import (
    AUDIO_DIMENSIONS,
    VIDEO_DIMENSIONS,
    MediaEvidence,
    MediaInterval,
    MediaReview,
)

COMMON_CHECKS = frozenset(
    """
correctness.source_match correctness.conventions
clarity.spoken_referents clarity.terms_defined clarity.no_meta
cognitive_load.one_change cognitive_load.external_state
coverage.media_mapping coverage.dependencies_disclosed
intuition.reasons intuition.limits
organization.media_sequence organization.chapters
redundancy.media_filler redundancy.caption_exception
delivery.intelligible delivery.pronunciation delivery.complete delivery.joins delivery.pace
representation.fidelity representation.form representation.layout representation.legibility
representation.focus representation.convention representation.shown_not_described
representation.state_fidelity
synchronization.referent synchronization.captions synchronization.reveal
""".split()
)
PROFILE_CHECKS = {
    "audio": frozenset(
        """
clarity.audio_independence organization.audio_rejoin intuition.revision_decision
redundancy.useful_reinforcement delivery.condition_emphasis
""".split()
    ),
    "concept": frozenset(
        """
intuition.visual_construction representation.correspondence organization.visual_thread
cognitive_load.reorientation redundancy.complementary_explanations
organization.lesson_overview organization.knowledge_points organization.lesson_closure
""".split()
    ),
    "exercise": frozenset(
        """
correctness.statement_fidelity coverage.exercise_demands intuition.method_choice
intuition.local_mechanism representation.working_shown representation.problem_correspondence
correctness.result_verified redundancy.exercise_scope synchronization.step_reveal
organization.exercise_setup representation.answer_emphasis
""".split()
    ),
}


def _complete(intervals: list[MediaInterval], duration: float, tolerance: float) -> bool:
    covered = 0.0
    for interval in sorted(intervals, key=lambda item: item.start):
        if interval.start > covered + tolerance:
            return False
        covered = max(covered, interval.end)
    return covered >= duration - tolerance


def _evidence(
    root: Path,
    item: MediaItem,
    review: MediaReview,
) -> tuple[set[str], list[str]]:
    accepted: list[MediaEvidence] = []
    errors = []
    tolerance = 1 / 30 if item.modality == "video" else 0.05
    for entry in review.evidence:
        if entry.artifact_sha256 != item.artifact_sha256:
            errors.append(f"{entry.kind}:artifact_changed")
            continue
        if any(interval.end > item.duration + tolerance for interval in entry.intervals):
            errors.append(f"{entry.kind}:interval_bounds")
            continue
        if entry.kind == "script" and entry.guidance_sha256 != item.guidance_sha256:
            errors.append("script:guidance_changed")
            continue
        try:
            file_hash(root, entry.path, entry.sha256)
        except (CampusError, OSError):
            errors.append(f"{entry.kind}:file_missing_or_changed:{entry.path}")
            continue
        accepted.append(entry)
    kinds = {entry.kind for entry in accepted if entry.kind not in {"listening", "playback"}}
    listening = [
        interval
        for entry in accepted
        if entry.kind == "listening" or (entry.kind == "playback" and entry.audio_perceived)
        for interval in entry.intervals
    ]
    playback = [
        interval for entry in accepted if entry.kind == "playback" for interval in entry.intervals
    ]
    if _complete(listening, item.duration, tolerance):
        kinds.add("listening")
    if _complete(playback, item.duration, tolerance):
        kinds.add("playback")
    required = {"script", "signal", "listening"}
    if item.modality == "video":
        required.update({"frames", "playback"})
    errors.extend(f"{kind}:incomplete" for kind in sorted(required - kinds))
    return kinds, errors


def _finding_errors(item: MediaItem, review: MediaReview) -> list[str]:
    errors = []
    errors.extend(
        f"visual_not_in_artifact:{visual.visual}"
        for visual in review.visuals
        if visual.visual not in item.visuals
    )
    checks = COMMON_CHECKS | PROFILE_CHECKS[item.profile]
    chapters = {chapter for chapter, _ in item.locations}
    beats = {beat for _, beat in item.locations if beat}
    targets = [
        *item.structure["targets"],
        *(f"study/{ref.split('/')[0]}" for ref in item.structure.get("prerequisites", [])),
    ]
    for finding in review.findings:
        if finding.check not in checks:
            errors.append(f"check_not_in_{item.profile}_profile:{finding.check}")
        if finding.end is not None and finding.end > item.duration:
            errors.append(f"finding_interval_bounds:{finding.check}")
        if finding.chapter and finding.chapter not in chapters:
            errors.append(f"finding_chapter_missing:{finding.chapter}")
        if finding.beat and finding.beat not in beats:
            errors.append(f"finding_beat_missing:{finding.beat}")
        if (
            finding.chapter
            and finding.beat
            and (finding.chapter, finding.beat) not in item.locations
        ):
            errors.append(f"finding_chapter_beat_mismatch:{finding.check}")
        if finding.source_locator and not any(
            finding.source_locator.startswith(f"{target}#") for target in targets
        ):
            errors.append(f"finding_source_not_in_target:{finding.check}")
    return errors


def media_report(
    root: Path | None,
    inventory: MediaInventory,
    reviews: tuple[MediaReview, ...],
) -> dict[str, JsonValue]:
    if root is None and (inventory.items or reviews):
        raise CampusError(Code.ACTION_REQUIRED, "Pass the course root to verify media evidence.")
    saved = {review.item: review for review in reviews}
    items, unreviewed, stale, unscored, missing, below = [], [], [], [], [], []
    invalid = list(inventory.invalid)
    checks: Counter[str] = Counter()
    averages: dict[str, dict[str, list[int]]] = {"audio": {}, "video": {}}
    for item in inventory.items:
        dimensions = AUDIO_DIMENSIONS if item.modality == "audio" else VIDEO_DIMENSIONS
        review = saved.get(item.item)
        fresh = review is not None and review.revision == item.revision
        if item.technical:
            invalid.append({"item": item.item, "checks": list(item.technical)})
        if item.stale or (review is not None and not fresh):
            stale.append(
                {
                    "item": item.item,
                    "revision": item.revision,
                    "reasons": [
                        *item.stale,
                        *(["review_revision_changed"] if review and not fresh else []),
                    ],
                }
            )
        kinds, evidence_errors = (
            _evidence(root, item, review)
            if review
            else (
                set(),
                [
                    "script:incomplete",
                    "signal:incomplete",
                    "listening:incomplete",
                    *(
                        ["frames:incomplete", "playback:incomplete"]
                        if item.modality == "video"
                        else []
                    ),
                ],
            )
        )
        if review is None:
            unreviewed.append({"item": item.item, "revision": item.revision})
        profile_errors = _finding_errors(item, review) if review else []
        if profile_errors:
            invalid.append({"item": item.item, "review": profile_errors})
        absent = {
            dimension
            for dimension in dimensions
            if review is None or dimension not in review.scores
        }
        if "script" not in kinds:
            absent.update(set(dimensions) - {"delivery", "representation", "synchronization"})
        if "listening" not in kinds:
            absent.add("delivery")
        if item.modality == "video":
            if "playback" not in kinds:
                absent.add("synchronization")
            visual_keys = {visual.visual for visual in review.visuals} if review else set()
            if "frames" not in kinds or set(item.visuals) - visual_keys:
                absent.add("representation")
            if not item.visuals:
                evidence_errors.append("frames:published_visual_mapping_missing")
                absent.add("representation")
        if absent:
            unscored.append(
                {
                    "item": item.item,
                    "dimensions": [d for d in dimensions if d in absent],
                    **(
                        {"visuals": sorted(set(item.visuals) - visual_keys)}
                        if item.modality == "video"
                        else {}
                    ),
                }
            )
        if evidence_errors:
            missing.append({"item": item.item, "evidence": evidence_errors})
        low = {d: score for d, score in review.scores.items() if score < 3} if fresh else {}
        blocked = bool(low and (not review.kept or 1 in low.values()))
        if low:
            below.append(
                {
                    "item": item.item,
                    "scores": low,
                    "findings": [f.model_dump(mode="json") for f in review.findings],
                    "blocked": blocked,
                    **({"kept": review.kept} if review.kept else {}),
                }
            )
        ready = not (item.stale or item.technical)
        passed = bool(
            fresh and ready and not (absent or evidence_errors or profile_errors or blocked)
        )
        items.append(
            {
                "item": item.item,
                "title": item.title,
                "modality": item.modality,
                "profile": item.profile,
                "revision": item.revision,
                "revision_inputs": item.projection,
                "source_targets": item.structure["targets"],
                "prerequisites": item.structure.get("prerequisites", []),
                "artifact_ready": ready,
                "required_dimensions": list(dimensions),
                "missing_evidence": evidence_errors,
                "visuals": list(item.visuals),
                "duration": item.duration,
                "artifact_sha256": item.artifact_sha256,
                "guidance_sha256": item.guidance_sha256,
                "passed": passed,
            }
        )
        if fresh and ready and not profile_errors:
            checks.update(f.check for f in review.findings)
            for dimension, score in review.scores.items():
                if dimension not in absent:
                    averages[item.modality].setdefault(dimension, []).append(score)
    removed = sorted(
        key
        for key in saved
        if key not in inventory.known
        and ("audio" if key.startswith("audio/") else "video") not in inventory.unreadable
    )
    return {
        "items": items,
        "pending": inventory.pending,
        "invalid": invalid,
        "unreviewed": unreviewed,
        "stale": stale,
        "unscored_dimensions": unscored,
        "missing_evidence": missing,
        "below_bar": below,
        "removed": removed,
        "averages": {
            kind: {
                dimension: round(sum(values) / len(values), 2)
                for dimension, values in scores.items()
            }
            for kind, scores in averages.items()
        },
        "failed_checks": dict(checks),
        "passed": not (
            inventory.pending
            or invalid
            or unreviewed
            or stale
            or unscored
            or missing
            or any(entry["blocked"] for entry in below)
        ),
    }
