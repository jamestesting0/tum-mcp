"""Read-only inventory of published media, desired work and exact review identities."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from tum_mcp.audio_content import (
    AudioChapters,
    AudioManifest,
    AudioPlan,
    AudioReceipt,
    AudioUnit,
    AudioValidation,
    category_hash,
)
from tum_mcp.errors import CampusError, Code
from tum_mcp.media_projection import MEDIA_RUBRIC_VERSION, file_hash, guidance_hash, source_problems
from tum_mcp.study_content import StudyContent
from tum_mcp.study_models import StudyState
from tum_mcp.study_store import confined
from tum_mcp.video_content import (
    ExerciseReceipt,
    Manifest,
    Receipt,
    VideoPlan,
    canonical,
    locator_fingerprint,
    semantic_hash,
    sha256,
    source_key,
)
from tum_mcp.video_project import _asset_digest, _hash_file, _read, load_style, load_voice
from tum_mcp.video_sources import VideoSources, read_sources
from tum_mcp.video_style import staged_bytes


@dataclass(frozen=True, slots=True)
class MediaItem:
    item: str
    modality: Literal["audio", "video"]
    profile: Literal["audio", "concept", "exercise"]
    title: str
    duration: float
    artifact_sha256: str
    projection: dict[str, JsonValue]
    structure: dict[str, JsonValue]
    stale: tuple[str, ...] = ()
    technical: tuple[str, ...] = ()
    visuals: tuple[str, ...] = ()
    locations: tuple[tuple[str, str], ...] = ()
    guidance_sha256: str = ""

    @property
    def revision(self) -> str:
        return sha256(canonical(self.projection))[:16]


@dataclass(slots=True)
class MediaInventory:
    items: list[MediaItem] = field(default_factory=list)
    pending: list[dict[str, JsonValue]] = field(default_factory=list)
    invalid: list[dict[str, JsonValue]] = field(default_factory=list)
    structure: list[dict[str, JsonValue]] = field(default_factory=list)
    known: set[str] = field(default_factory=set)
    unreadable: set[str] = field(default_factory=set)


def _bound(record: AudioManifest | AudioPlan | Manifest | VideoPlan, state: StudyState) -> None:
    if record.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "Media records belong to another course.")


def _audio_item(
    root: Path,
    state: StudyState,
    content: StudyContent,
    receipt: AudioReceipt,
) -> MediaItem:
    hashes = {
        name: file_hash(root, f"audio/{file.path}", file.sha256, file.size)
        for name, file in (
            ("script", receipt.script),
            ("track", receipt.track),
            ("chapters", receipt.chapters),
        )
    }
    file_hash(root, f"audio/{receipt.teaching_review.path}", receipt.teaching_review.sha256)
    file_hash(root, f"audio/{receipt.validation.path}", receipt.validation.sha256)
    chapters = _read(confined(root, f"audio/{receipt.chapters.path}"), AudioChapters)
    validation = _read(confined(root, f"audio/{receipt.validation.path}"), AudioValidation)
    if chapters is None or validation is None:
        raise CampusError(Code.INVALID_RESPONSE, "Audio chapter or validation record is missing.")
    for evidence in (validation.probe, validation.decode, validation.loudness):
        file_hash(root, f"audio/{evidence.path}", evidence.sha256)
    technical = []
    if validation.artifact_sha256 != hashes["track"]:
        technical.append("signal.artifact_identity")
    if validation.codec != "aac" or "m4a" not in validation.container.split(","):
        technical.append("signal.aac_m4a")
    if not validation.decoded:
        technical.append("signal.decode")
    if abs(validation.duration - receipt.duration) > 0.05:
        technical.append("signal.duration")
    if abs(validation.loudness_lufs + 16) > 1:
        technical.append("signal.loudness")
    if validation.true_peak_dbtp > -1.5:
        technical.append("signal.peak")
    if chapters.root[-1].end > receipt.duration + 0.05:
        technical.append("chapters.bounds")
    chapter_keys = {chapter.key for chapter in chapters.root}
    if any(entry.chapter not in chapter_keys for entry in receipt.coverage):
        technical.append("coverage.chapter")
    units = {unit.key: unit for unit in content.units}
    current_units = tuple(
        AudioUnit(unit=entry.unit, semantic_sha256=semantic_hash(units[entry.unit]))
        for entry in receipt.units
        if entry.unit in units
    )
    stale = list(source_problems(root, state, receipt.source_references))
    if category_hash(receipt.title, current_units) != receipt.category_sha256:
        stale.append("teaching_changed")
    for entry in receipt.coverage:
        unit = units.get(entry.unit)
        if unit is None or locator_fingerprint(unit, entry.locator) != entry.locator.fingerprint:
            stale.append(f"coverage_changed:{entry.unit}/{entry.locator.ref}")
        if entry.mode == "missing":
            stale.append(f"coverage_missing:{entry.unit}/{entry.locator.ref}")
    references = {
        (source.key, source.sha256)
        for entry in receipt.units
        if entry.unit in units
        for source in units[entry.unit].sources
    }
    if references != {(source.key, source.sha256) for source in receipt.source_references}:
        stale.append("source_references_changed")
    guide = guidance_hash("audio")
    projection = {
        "rubric": MEDIA_RUBRIC_VERSION,
        "profile": "audio",
        "key": receipt.key,
        "title": receipt.title,
        "units": [unit.model_dump(mode="json") for unit in current_units],
        "sources": [source.model_dump(mode="json") for source in receipt.source_references],
        "files": hashes,
        "voice": receipt.voice.model_dump(mode="json"),
        "chunks": [chunk.model_dump(mode="json") for chunk in receipt.chunk_inputs],
        "coverage": [entry.model_dump(mode="json") for entry in receipt.coverage],
        "validation": receipt.validation.sha256,
        "teaching_review": receipt.teaching_review.sha256,
        "teaching_guidance": receipt.teaching_review.guidance_sha256,
        "guidance": guide,
    }
    structure = {
        "item": f"audio/{receipt.key}",
        "targets": [f"study/{u.unit}" for u in receipt.units],
        "chapters": [{"key": c.key, "title": c.title} for c in chapters.root],
        "coverage": [
            {
                "unit": entry.unit,
                "locator": entry.locator.ref,
                "chapter": entry.chapter,
                "mode": entry.mode,
            }
            for entry in receipt.coverage
        ],
        "available": True,
    }
    return MediaItem(
        f"audio/{receipt.key}",
        "audio",
        "audio",
        receipt.title,
        receipt.duration,
        hashes["track"],
        projection,
        structure,
        tuple(dict.fromkeys(stale)),
        tuple(technical),
        guidance_sha256=guide,
        locations=tuple((chapter.key, "") for chapter in chapters.root),
    )


def _video_item(
    root: Path,
    state: StudyState,
    receipt: Receipt | ExerciseReceipt,
    inventory: VideoSources,
) -> MediaItem:
    hashes = {
        name: file_hash(root, f"videos/{file.path}", file.sha256, file.size)
        for name, file in receipt.files.items()
    }
    source = inventory.items.get(source_key(receipt))
    stale = []
    if source is None:
        stale.append("source_removed_or_moved")
    else:
        stale.extend(source_problems(root, state, source.source_references))
    match receipt:
        case Receipt():
            published_hash = receipt.unit_hash
            profile = "concept"
            links = [f"study/{receipt.unit}"]
        case ExerciseReceipt():
            published_hash = receipt.exercise_hash
            profile = "exercise"
            links = [source_key(receipt)]
            if source and any(
                source.locator_hash(p) != p.fingerprint for p in receipt.prerequisites
            ):
                stale.append("prerequisite_changed")
            if source and receipt.solution_origin != source.data.solution.origin:
                stale.append("solution_origin_changed")
    if source and source.teaching_hash != published_hash:
        stale.append("teaching_changed")
    if source and receipt.source_references != source.source_references:
        stale.append("source_references_changed")
    current_style = sha256(staged_bytes(load_style(root)))
    current_voice = load_voice(root).profiles.get(receipt.voice_profile_key)
    if receipt.inputs["style"] != current_style:
        stale.append("style_changed")
    if receipt.voice_profile is not None:
        if current_voice != receipt.voice_profile:
            stale.append("voice_changed")
    current_inputs = dict(receipt.inputs)
    story = confined(root, f"videos/storyboards/{receipt.stem}.json")
    if story.is_file():
        current_inputs["storyboard"] = _hash_file(story)
        if current_inputs["storyboard"] != receipt.inputs["storyboard"]:
            stale.append("storyboard_edited")
    scene = confined(root, f"videos/scenes/{receipt.stem}/chapters.py")
    assets = receipt.assets_sha256
    if scene.is_file():
        current_inputs["scene"] = _hash_file(scene)
        if current_inputs["scene"] != receipt.inputs["scene"]:
            stale.append("scene_edited")
        assets = _asset_digest(root, scene.read_text(encoding="utf-8"))
        if receipt.assets_sha256 is not None and assets != receipt.assets_sha256:
            stale.append("assets_changed")
    if receipt.teaching_review_sha256 is not None:
        file_hash(root, f"videos/{receipt.teaching_review}", receipt.teaching_review_sha256)
    try:
        chapter_file = json.loads(
            confined(root, f"videos/{receipt.files['chapter_index'].path}").read_bytes()
        )
    except (ValueError, UnicodeError):
        raise CampusError(Code.INVALID_RESPONSE, "Invalid published video chapter index.") from None
    if chapter_file != [
        chapter.model_dump(mode="json", exclude={"answer"}) for chapter in receipt.chapters
    ]:
        raise CampusError(
            Code.INVALID_RESPONSE, "Published video chapters differ from their receipt."
        )
    guide = guidance_hash("video")
    projection = {
        "rubric": MEDIA_RUBRIC_VERSION,
        "profile": profile,
        "source": source_key(receipt),
        "source_hash": source.teaching_hash if source else None,
        "files": hashes,
        "inputs": current_inputs,
        "assets": assets,
        "current_style": current_style,
        "voice": receipt.voice_profile.model_dump(mode="json") if receipt.voice_profile else None,
        "current_voice": current_voice.model_dump(mode="json") if current_voice else None,
        "source_references": [
            reference.model_dump(mode="json") for reference in source.source_references
        ]
        if source
        else [],
        "prerequisites": [
            {"ref": p.ref, "fingerprint": source.locator_hash(p) if source else None}
            for p in receipt.prerequisites
        ]
        if isinstance(receipt, ExerciseReceipt)
        else [],
        "guidance": guide,
        "published_guidance": receipt.guidance_sha256,
        "teaching_review": receipt.teaching_review_sha256,
        "duration": receipt.duration,
        "chapters": [chapter.model_dump(mode="json") for chapter in receipt.chapters],
        "beats": [beat.model_dump(mode="json") for beat in receipt.beats],
        "visuals": list(receipt.visuals),
    }
    structure = {
        "item": f"video/{receipt.stem}",
        "targets": links,
        "available": True,
        "chapters": [{"key": c.key, "title": c.title} for c in receipt.chapters],
        "prerequisites": [p.ref for p in receipt.prerequisites]
        if isinstance(receipt, ExerciseReceipt)
        else [],
    }
    required = {
        "container.mp4",
        "video.h264",
        "video.yuv420p",
        "video.size",
        "video.fps",
        "video.duration",
        "mp4.faststart",
        "audio.aac",
        "audio.format",
        "audio.sync",
        "audio.loudness",
        "audio.true_peak",
        "captions.valid",
        "captions.ordered",
        "captions.bounds",
        "chapters.valid",
        "chapters.ordered",
        "chapters.bounds",
        "poster.jpeg",
        "layout.clear",
    }
    technical = tuple(sorted(required - set(receipt.checks)))
    if not receipt.narrated:
        technical = (*technical, "narration.present")
    if receipt.voice_profile is None or receipt.voice_profile_key is None:
        technical = (*technical, "snapshot.voice")
    if receipt.assets_sha256 is None:
        technical = (*technical, "snapshot.assets")
    if not receipt.beats:
        technical = (*technical, "snapshot.beats")
    return MediaItem(
        f"video/{receipt.stem}",
        "video",
        profile,
        receipt.title,
        receipt.duration,
        hashes["track"],
        projection,
        structure,
        tuple(dict.fromkeys(stale)),
        technical,
        receipt.visuals,
        tuple((b.chapter, b.key) for b in receipt.beats),
        guide,
    )


def discover(root: Path, state: StudyState, content: StudyContent | None) -> MediaInventory:
    result = MediaInventory()
    for modality, manifest_model, plan_model in (
        ("audio", AudioManifest, AudioPlan),
        ("video", Manifest, VideoPlan),
    ):
        folder = "audio" if modality == "audio" else "videos"
        manifest = None
        plan = None
        for name, model in (("manifest", manifest_model), ("plan", plan_model)):
            relative = f"{folder}/{name}.json"
            try:
                record = _read(confined(root, relative), model)
                if record is not None:
                    _bound(record, state)
                if name == "manifest":
                    manifest = record
                else:
                    plan = record
            except (CampusError, OSError) as error:
                result.invalid.append({"path": relative, "note": str(error)})
                result.unreadable.add(modality)
        source_inventory = None
        if (isinstance(manifest, Manifest) and manifest.videos) or (
            isinstance(plan, VideoPlan) and plan.videos
        ):
            try:
                source_inventory = read_sources(root)
            except (CampusError, OSError) as error:
                result.invalid.append(
                    {
                        "path": "videos/manifest.json"
                        if isinstance(manifest, Manifest) and manifest.videos
                        else "videos/plan.json",
                        "note": str(error),
                    }
                )
        match manifest:
            case AudioManifest():
                for key, receipt in manifest.categories.items():
                    result.known.add(f"audio/{key}")
                    try:
                        if content is None:
                            raise CampusError(
                                Code.ACTION_REQUIRED, "Audio requires prepared Study."
                            )
                        item = _audio_item(root, state, content, receipt)
                        result.items.append(item)
                        result.structure.append(item.structure)
                    except (CampusError, OSError) as error:
                        result.invalid.append({"item": f"audio/{key}", "note": str(error)})
                        result.structure.append(
                            {
                                "item": f"audio/{key}",
                                "targets": [f"study/{u.unit}" for u in receipt.units],
                                "available": False,
                            }
                        )
            case Manifest():
                result.known.update(f"video/{stem}" for stem in manifest.videos)
                if source_inventory is not None:
                    for stem, receipt in manifest.videos.items():
                        try:
                            item = _video_item(root, state, receipt, source_inventory)
                            result.items.append(item)
                            result.structure.append(item.structure)
                        except (CampusError, OSError, SyntaxError, UnicodeError) as error:
                            result.invalid.append({"item": f"video/{stem}", "note": str(error)})
                            result.structure.append(
                                {
                                    "item": f"video/{stem}",
                                    "targets": [source_key(receipt)],
                                    "available": False,
                                }
                            )
        match plan:
            case AudioPlan():
                published = manifest.categories if isinstance(manifest, AudioManifest) else {}
                previous_homes = {
                    u.unit: key for key, category in published.items() for u in category.units
                }
                desired_homes = {
                    u.unit: key
                    for key, category in plan.categories.items()
                    if category.pending != "removed"
                    for u in category.units
                }
                moved = {
                    unit
                    for unit, home in desired_homes.items()
                    if unit in previous_homes and previous_homes[unit] != home
                }
                known_units = {unit.key for unit in content.units} if content else set()
                for key in (
                    *plan.category_order,
                    *(k for k in plan.categories if k not in plan.category_order),
                ):
                    desired = plan.categories[key]
                    old = published.get(key)
                    actual = next((i for i in result.items if i.item == f"audio/{key}"), None)
                    affected_units = {u.unit for u in desired.units}
                    if old:
                        affected_units.update(u.unit for u in old.units)
                    if (
                        desired.pending == "removed"
                        or not {u.unit for u in desired.units} <= known_units
                    ):
                        reason = "removed"
                    elif moved & affected_units:
                        reason = "moved"
                    elif old is None:
                        reason = "new"
                    elif actual is None:
                        reason = "missing"
                    elif (
                        old.category_sha256 != desired.category_sha256
                        or old.coverage != desired.coverage
                        or old.stem != desired.stem
                        or (desired.voice is not None and old.voice != desired.voice)
                        or actual.stale
                        or actual.technical
                    ):
                        reason = "changed"
                    else:
                        reason = "none"
                    if reason != "none":
                        result.pending.append({"item": f"audio/{key}", "reason": reason})
                    result.structure.append(
                        {
                            "item": f"audio/{key}",
                            "targets": [f"study/{u.unit}" for u in desired.units],
                            "pending": reason,
                            "order": list(plan.category_order).index(key)
                            if key in plan.category_order
                            else None,
                        }
                    )
            case VideoPlan():
                for desired in plan.videos:
                    identity = source_key(desired)
                    if desired.decision == "text-first":
                        result.structure.append({"source": identity, "decision": "text-first"})
                        continue
                    key = f"video/{desired.stem}"
                    old = (
                        manifest.videos.get(desired.stem)
                        if isinstance(manifest, Manifest)
                        else None
                    )
                    actual = next((i for i in result.items if i.item == key), None)
                    reason = (
                        "missing"
                        if source_inventory is None
                        else "removed"
                        if identity not in source_inventory.items
                        else "changed"
                        if old is not None and source_key(old) != identity
                        else "removed"
                        if actual is not None and "source_removed_or_moved" in actual.stale
                        else "new"
                        if old is None
                        else "missing"
                        if actual is None
                        else ("changed" if actual.stale else "none")
                    )
                    if reason != "none":
                        result.pending.append({"item": key, "source": identity, "reason": reason})
                    result.structure.append({"item": key, "targets": [identity], "pending": reason})
    return result
