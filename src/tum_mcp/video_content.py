"""Video Notes contracts: storyboards, records and prepared-content fingerprints."""

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, JsonValue, field_validator, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_content import StudyContent, Unit
from tum_mcp.study_models import Digest, Key

Stem = Annotated[str, Field(pattern=r"^\d{2,3}_[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)]
ChapterKey = Annotated[str, Field(pattern=r"^c\d{2}$")]
BeatKey = Annotated[str, Field(pattern=r"^b\d{2,3}$")]
Language = Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")]
Sentence = Annotated[str, Field(min_length=1, max_length=600, pattern=r"^[^\r\n]+$")]
Short = Annotated[str, Field(min_length=1, max_length=150, pattern=r"^[^\r\n]+$")]
Prose = Annotated[str, Field(min_length=1, max_length=600)]
Seconds = Annotated[float, Field(ge=0, le=36000, allow_inf_nan=False)]
Color = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]

WORDS_PER_SECOND = 2.33
BEAT_LEAD_IN = 0.25
SENTENCE_GAP = 0.3
BEAT_TAIL = 0.2
SOFT_LIMIT_SECONDS = 600


def canonical(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _teaching(value: JsonValue) -> JsonValue:
    """Drop provenance and pure diagram layout so only taught meaning is fingerprinted."""
    if isinstance(value, dict):
        kind = value.get("kind")
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if key == "sources":
                continue
            if kind == "diagram" and key == "nodes" and isinstance(item, list):
                result[key] = [
                    {k: v for k, v in node.items() if k not in {"x", "y", "shape"}}
                    if isinstance(node, dict)
                    else node
                    for node in item
                ]
                continue
            result[key] = _teaching(item)
        return result
    if isinstance(value, list):
        return [_teaching(item) for item in value]
    return value


def semantic_hash(unit: Unit) -> str:
    value = unit.model_dump(
        mode="json", exclude_none=True, exclude={"path", "label", "minutes", "sources"}
    )
    return sha256(canonical(_teaching(value)))


def fingerprint(value: Frozen) -> str:
    return sha256(canonical(_teaching(value.model_dump(mode="json", exclude_none=True))))


def unit_revision(unit: Unit) -> str:
    from tum_mcp.study_build import unit_revision as app_revision

    return app_revision(unit)


class Locator(Frozen):
    kind: Literal["block", "flashcard", "question", "objective", "summary"]
    ref: Annotated[str, Field(min_length=1, max_length=120)]
    fingerprint: Digest

    @model_validator(mode="after")
    def reference(self) -> "Locator":
        if self.kind == "block" and re.fullmatch(r"blocks\[(\d|[1-3]\d)\]", self.ref) is None:
            raise ValueError("Block locators use blocks[N].")
        if self.kind == "summary" and self.ref != "summary":
            raise ValueError("Summary locators use ref 'summary'.")
        if self.kind in {"flashcard", "question", "objective"} and (
            re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,99}", self.ref) is None
        ):
            raise ValueError("Item locators use the item's key.")
        return self


def _no_typst_code(value: str) -> str:
    # `#` switches Typst math into code mode (#import, #read, #image, #include, ...).
    if "#" in value:
        raise ValueError("Typst math may not contain '#' code expressions.")
    return value


TypstMath = Annotated[str, Field(min_length=1, max_length=600)]


class OnScreen(Frozen):
    key: Key
    kind: Literal["label", "math", "number", "code"]
    text: Short | None = None
    typst: TypstMath | None = None
    source_latex: Annotated[str, Field(min_length=1, max_length=5000)] | None = None
    value: float | None = Field(default=None, allow_inf_nan=False, ge=-1e12, le=1e12)
    decimals: int = Field(default=0, ge=0, le=6)
    unit: Annotated[str, Field(max_length=20, pattern=r"^[^\r\n]*$")] = ""
    code: Annotated[str, Field(min_length=1, max_length=4000)] | None = None
    language: Annotated[str, Field(pattern=r"^[a-z0-9+#-]{1,30}$")] | None = None

    @field_validator("typst")
    @classmethod
    def safe_typst(cls, value: str | None) -> str | None:
        return None if value is None else _no_typst_code(value)

    @model_validator(mode="after")
    def shape(self) -> "OnScreen":
        present = {
            "label": self.text is not None,
            "math": self.typst is not None,
            "number": self.value is not None,
            "code": self.code is not None and self.language is not None,
        }
        if not present[self.kind] or any(v for k, v in present.items() if k != self.kind):
            raise ValueError(f"On-screen {self.kind} items need exactly their own fields.")
        if self.source_latex is not None and self.kind != "math":
            raise ValueError("Only math items carry source_latex.")
        if self.code is not None:
            lines = self.code.split("\n")
            if len(lines) > 40 or any(len(line) > 100 or "\r" in line for line in lines):
                raise ValueError("Code items allow 40 lines of at most 100 characters.")
        return self


class Beat(Frozen):
    key: BeatKey
    kind: Literal[
        "hook", "bridge", "instance", "mechanism", "generalize", "pitfall", "question", "recap"
    ]
    narration: tuple[Sentence, ...] = Field(default=(), max_length=12)
    pause_s: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    on_screen: tuple[OnScreen, ...] = Field(default=(), max_length=40)
    locators: tuple[Locator, ...] = Field(min_length=1, max_length=20)
    question: Key | None = None
    intent: Prose
    layout_waiver: Annotated[str, Field(min_length=10, max_length=300)] | None = None

    @model_validator(mode="after")
    def timing(self) -> "Beat":
        if not self.narration and self.pause_s < 0.5:
            raise ValueError("A beat without narration needs an intentional pause of 0.5 s+.")
        if self.kind == "question":
            if self.question is None or self.pause_s < 2:
                raise ValueError("Question beats name an existing question and pause 2-10 s.")
        elif self.question is not None:
            raise ValueError("Only question beats reference a practice question.")
        return self


class Chapter(Frozen):
    key: ChapterKey
    title: Short
    beats: tuple[Beat, ...] = Field(min_length=1, max_length=40)


class Storyboard(Frozen):
    schema_version: Literal[1] = 1
    video: Stem
    unit: Key
    unit_hash: Digest
    title: Short
    language: Language
    objectives: tuple[Key, ...] = Field(min_length=1, max_length=12)
    chapters: tuple[Chapter, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique(self) -> "Storyboard":
        chapters = [chapter.key for chapter in self.chapters]
        beats = [beat.key for beat in self.beats()]
        screens = [item.key for beat in self.beats() for item in beat.on_screen]
        if len(set(chapters)) != len(chapters) or chapters != sorted(chapters):
            raise ValueError("Chapter keys must be unique and in ascending order.")
        if len(set(beats)) != len(beats) or beats != sorted(beats, key=lambda k: int(k[1:])):
            raise ValueError("Beat keys must be unique and ascend across the video.")
        if len(set(screens)) != len(screens) or len(screens) > 300:
            raise ValueError("On-screen keys must be unique across the video (max 300).")
        if len(set(self.objectives)) != len(self.objectives):
            raise ValueError("Covered objectives must be unique.")
        return self

    def beats(self) -> tuple[Beat, ...]:
        return tuple(beat for chapter in self.chapters for beat in chapter.beats)

    def screen(self) -> dict[str, OnScreen]:
        return {item.key: item for beat in self.beats() for item in beat.on_screen}


class StoryboardReport(Frozen):
    video: Stem
    unit: Key
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    estimated_seconds: float
    words: int


def _resolve(unit: Unit, locator: Locator) -> Frozen | str | None:
    match locator.kind:
        case "block":
            index = int(locator.ref[7:-1])
            return unit.blocks[index] if index < len(unit.blocks) else None
        case "flashcard":
            return next((item for item in unit.flashcards if item.key == locator.ref), None)
        case "question":
            return next((item for item in unit.questions if item.key == locator.ref), None)
        case "objective":
            return next((item for item in unit.objectives if item.key == locator.ref), None)
        case "summary":
            return unit.summary


def locator_fingerprint(unit: Unit, locator: Locator) -> str | None:
    value = _resolve(unit, locator)
    if value is None:
        return None
    if isinstance(value, str):
        return sha256(canonical(value))
    return fingerprint(value)


def estimate_seconds(storyboard: Storyboard) -> tuple[float, int]:
    words = sum(len(s.split()) for beat in storyboard.beats() for s in beat.narration)
    seconds = 0.0
    for beat in storyboard.beats():
        spoken = sum(len(s.split()) for s in beat.narration) / WORDS_PER_SECOND
        gaps = SENTENCE_GAP * max(0, len(beat.narration) - 1)
        seconds += (BEAT_LEAD_IN + BEAT_TAIL if beat.narration else 0) + spoken + gaps
        seconds += beat.pause_s
    return round(seconds, 1), words


def check_storyboard(storyboard: Storyboard, content: StudyContent) -> StoryboardReport:
    errors: list[str] = []
    warnings: list[str] = []
    unit = next((item for item in content.units if item.key == storyboard.unit), None)
    if unit is None:
        errors.append(f"unit.missing: prepared content has no unit '{storyboard.unit}'")
    else:
        if storyboard.unit_hash != semantic_hash(unit):
            errors.append(
                "unit.stale: the unit's teaching changed since this storyboard was planned; "
                "re-read it and update unit_hash only after revising affected beats"
            )
        objectives = {item.key for item in unit.objectives}
        questions = {item.key: item for item in unit.questions}
        cards = {item.key: item for item in unit.flashcards}
        mapped: set[str] = set()
        for beat in storyboard.beats():
            for locator in beat.locators:
                actual = locator_fingerprint(unit, locator)
                if actual is None:
                    errors.append(f"locator.missing {beat.key}: {locator.kind} {locator.ref}")
                elif actual != locator.fingerprint:
                    errors.append(f"locator.changed {beat.key}: {locator.kind} {locator.ref}")
                if locator.kind == "objective":
                    mapped.add(locator.ref)
                elif locator.kind == "question" and locator.ref in questions:
                    mapped.add(questions[locator.ref].objective)
                elif locator.kind == "flashcard" and locator.ref in cards:
                    mapped.add(cards[locator.ref].objective)
            if beat.question is not None and beat.question not in questions:
                errors.append(f"question.missing {beat.key}: {beat.question}")
        for key in storyboard.objectives:
            if key not in objectives:
                errors.append(f"objective.missing: {key}")
            elif key not in mapped:
                errors.append(f"objective.unmapped: {key} has no beat locator")
        uncovered = sorted(objectives - set(storyboard.objectives))
        if uncovered:
            warnings.append("objective.not_in_video: " + ", ".join(uncovered))
    seconds, words = estimate_seconds(storyboard)
    if seconds > SOFT_LIMIT_SECONDS:
        warnings.append(
            f"length.long: about {seconds / 60:.1f} min; consider splitting the unit "
            "in prepare-study"
        )
    if not any(beat.kind == "question" for beat in storyboard.beats()):
        warnings.append("retrieval.none: no pause-and-ponder question beat")
    return StoryboardReport(
        video=storyboard.video,
        unit=storyboard.unit,
        errors=tuple(errors),
        warnings=tuple(warnings),
        estimated_seconds=seconds,
        words=words,
    )


def transcript(storyboard: Storyboard) -> str:
    lines = [storyboard.title, ""]
    for chapter in storyboard.chapters:
        lines.append(chapter.title)
        spoken = " ".join(s for beat in chapter.beats for s in beat.narration)
        lines.extend((spoken or "(No narration.)", ""))
    return "\n".join(lines).rstrip() + "\n"


def slug(title: str, fallback: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_text.lower())
    value = "-".join(words)[:40].strip("-")
    return value or re.sub(r"[^a-z0-9]+", "-", fallback).strip("-")[:40] or "video"


class PlannedVideo(Frozen):
    unit: Key
    decision: Literal["video", "text-first"]
    reason: Prose
    stem: Stem | None = None

    @model_validator(mode="after")
    def stem_for_video(self) -> "PlannedVideo":
        if (self.decision == "video") != (self.stem is not None):
            raise ValueError("Only planned videos carry a stem.")
        return self


class VideoPlan(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    content_sha256: Digest
    videos: tuple[PlannedVideo, ...] = Field(default=(), max_length=300)

    @model_validator(mode="after")
    def unique(self) -> "VideoPlan":
        units = [item.unit for item in self.videos]
        stems = [item.stem for item in self.videos if item.stem]
        prefixes = [stem.split("_", 1)[0] for stem in stems]
        if len(set(units)) != len(units) or len(set(stems)) != len(stems):
            raise ValueError("Each unit and stem appears once in the plan.")
        if len(set(prefixes)) != len(prefixes):
            raise ValueError("Video number prefixes must be unique.")
        return self


class Selection(Frozen):
    unit: Key
    decision: Literal["video", "text-first"]
    reason: Prose


class SelectionFile(Frozen):
    units: tuple[Selection, ...] = Field(min_length=1, max_length=300)


def allocate(
    previous: VideoPlan | None,
    selections: tuple[Selection, ...],
    content: StudyContent,
    occupied: frozenset[str] = frozenset(),
    published: dict[str, str] | None = None,
) -> tuple[PlannedVideo, ...]:
    """Keep planned or published stems; new videos get the next unused number and a slug."""
    units = {unit.key: unit for unit in content.units}
    old = {item.unit: item for item in previous.videos} if previous else {}
    chosen = {item.unit: item for item in selections}
    if len(chosen) != len(selections):
        raise ValueError("Each unit may be selected once.")
    missing = sorted(set(chosen) - set(units))
    if missing:
        raise ValueError("Unknown units: " + ", ".join(missing))
    used = {item.stem for item in old.values() if item.stem} | set(occupied)
    numbers = {int(stem.split("_", 1)[0]) for stem in used}
    result: dict[str, PlannedVideo] = dict(old)
    for unit in content.units:
        selection = chosen.get(unit.key)
        if selection is None:
            continue
        stem = old[unit.key].stem if unit.key in old else None
        if selection.decision == "video" and stem is None:
            stem = (published or {}).get(unit.key)
        if selection.decision == "video" and stem is None:
            number = next(n for n in range(1, 1000) if n not in numbers)
            numbers.add(number)
            candidate = f"{number:02d}_{slug(unit.title, unit.key)}"
            if any(s.split("_", 1)[1] == candidate.split("_", 1)[1] for s in used):
                candidate = f"{number:02d}_{slug(unit.title + ' ' + unit.key, unit.key)}"
            stem = candidate
            used.add(stem)
        result[unit.key] = PlannedVideo(
            unit=unit.key,
            decision=selection.decision,
            reason=selection.reason,
            stem=stem if selection.decision == "video" else None,
        )
    order = {unit.key: index for index, unit in enumerate(content.units)}
    return tuple(sorted(result.values(), key=lambda item: order.get(item.unit, math.inf)))


class StyleProfile(Frozen):
    schema_version: Literal[1] = 1
    theme: Literal["dark", "light"] = "dark"
    math: Literal["typst", "latex"] = "typst"
    symbol_colors: dict[Annotated[str, Field(min_length=1, max_length=40)], Color] = Field(
        default_factory=dict, max_length=64
    )


class VoiceProfile(Frozen):
    provider: Annotated[str, Field(min_length=1, max_length=60)]
    route: Annotated[str, Field(min_length=1, max_length=120)]
    voice: Annotated[str, Field(min_length=1, max_length=120)]
    language: Language
    model: Annotated[str, Field(min_length=1, max_length=120)] = "unknown"
    settings: dict[Key, JsonValue] = Field(default_factory=dict, max_length=30)


class VoiceFile(Frozen):
    schema_version: Literal[1] = 1
    preferred: Annotated[str, Field(max_length=300)] = (
        "ElevenLabs free website when it works; otherwise local Kokoro"
    )
    profiles: dict[Key, VoiceProfile] = Field(default_factory=dict, max_length=20)
    pronunciation: dict[Annotated[str, Field(min_length=1, max_length=60)], Short] = Field(
        default_factory=dict, max_length=300
    )


def voice_tag(key: str, profile: VoiceProfile) -> str:
    return f"{key}@{sha256(canonical(profile.model_dump(mode='json')))[:16]}"


def chunk_name(beat: str, index: int, text: str, voice: str) -> str:
    return f"{beat}_{index:02d}-{sha256(canonical([text, voice]))[:10]}"


class Cue(Frozen):
    start: Seconds
    end: Seconds
    text: Sentence
    audio: (
        Annotated[str, Field(pattern=r"^b\d{2,3}_\d{2}-[a-f0-9]{10}\.(wav|mp3|m4a|flac|ogg)$")]
        | None
    ) = None


class BeatTiming(Frozen):
    key: BeatKey
    chapter: ChapterKey
    start: Seconds
    duration: Seconds
    cues: tuple[Cue, ...] = ()


class Timing(Frozen):
    schema_version: Literal[1] = 1
    video: Stem
    storyboard_sha256: Digest
    voice: Annotated[str, Field(pattern=r"^(silent|[a-z0-9][a-z0-9_.-]{0,99}@[a-f0-9]{16})$")]
    beats: tuple[BeatTiming, ...] = Field(min_length=1, max_length=480)
    total: Seconds

    @property
    def silent(self) -> bool:
        return self.voice == "silent"


def compose_timing(
    storyboard: Storyboard,
    storyboard_sha256: str,
    voice: str,
    durations: dict[str, tuple[float, str | None]],
) -> Timing:
    beats: list[BeatTiming] = []
    clock = 0.0
    for chapter in storyboard.chapters:
        for beat in chapter.beats:
            start = clock
            cues: list[Cue] = []
            if beat.narration:
                clock += BEAT_LEAD_IN
                for index, sentence in enumerate(beat.narration, 1):
                    if index > 1:
                        clock += SENTENCE_GAP
                    length, audio = durations[f"{beat.key}/{index}"]
                    cues.append(
                        Cue(
                            start=round(clock, 3),
                            end=round(clock + length, 3),
                            text=sentence,
                            audio=audio,
                        )
                    )
                    clock += length
                clock += BEAT_TAIL
            clock += beat.pause_s
            beats.append(
                BeatTiming(
                    key=beat.key,
                    chapter=chapter.key,
                    start=round(start, 3),
                    duration=round(clock - start, 3),
                    cues=tuple(cues),
                )
            )
    return Timing(
        video=storyboard.video,
        storyboard_sha256=storyboard_sha256,
        voice=voice,
        beats=tuple(beats),
        total=round(clock, 3),
    )


class FileReceipt(Frozen):
    path: Annotated[str, Field(pattern=r"^[a-z]+/[0-9a-z_.-]+$", max_length=120)]
    sha256: Digest
    size: int = Field(ge=1, le=8 * 1024**3)


class ChapterBound(Frozen):
    key: ChapterKey
    title: Short
    start: Seconds
    end: Seconds


class Receipt(Frozen):
    stem: Stem
    unit: Key
    title: Short
    language: Language
    made_for_revision: Digest
    unit_hash: Digest
    inputs: dict[Literal["storyboard", "scene", "style", "timing", "voice"], Digest]
    render_profile: Annotated[str, Field(min_length=1, max_length=120)]
    narrated: bool
    duration: Seconds
    chapters: tuple[ChapterBound, ...] = Field(min_length=1, max_length=12)
    files: dict[
        Literal["track", "captions", "chapters", "chapter_index", "poster", "transcript"],
        FileReceipt,
    ]
    objectives: tuple[Key, ...]
    checks: tuple[Annotated[str, Field(max_length=200)], ...]
    teaching_review: Annotated[str, Field(max_length=200)]
    visual_review: Literal["performed", "not_performed"]
    run: Annotated[str, Field(pattern=r"^r-[a-f0-9]{8}$")]
    published_at: AwareDatetime
    reviews: tuple[Annotated[str, Field(max_length=200)], ...] = ()


class Manifest(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    videos: dict[Stem, Receipt] = Field(default_factory=dict, max_length=300)

    @model_validator(mode="after")
    def consistent(self) -> "Manifest":
        if any(stem != receipt.stem for stem, receipt in self.videos.items()):
            raise ValueError("Manifest keys must match receipt stems.")
        units = [receipt.unit for receipt in self.videos.values()]
        if len(set(units)) != len(units):
            raise ValueError("Each unit has at most one published video.")
        return self


def now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
