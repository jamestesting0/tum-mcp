"""Course-local Audio Notes: sources, category scripts, narration chunks and publication."""

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from filelock import FileLock, Timeout
from pydantic import Field, model_validator

from tum_mcp.course.content.exam import ExamContent
from tum_mcp.course.content.study import StudyContent
from tum_mcp.course.media.audio import (
    AudioChapter,
    AudioChapters,
    AudioCoverage,
    AudioFile,
    AudioManifest,
    AudioPlan,
    AudioReceipt,
    AudioTool,
    AudioUnit,
    AudioValidation,
    ChunkInput,
    MediaFile,
    PlannedAudio,
    SourceKind,
    TeachingReviewFile,
    category_hash,
    exam_hash,
    exam_item,
)
from tum_mcp.course.media.video_content import (
    Locator,
    Sentence,
    Short,
    Stem,
    VoiceFile,
    VoiceProfile,
    canonical,
    chunk_name,
    locator_fingerprint,
    semantic_hash,
    sha256,
    voice_tag,
)
from tum_mcp.course.media.video_project import AUDIO_EXTENSIONS, _hash_file, _read, _write_json
from tum_mcp.course.project.models import Key
from tum_mcp.course.project.store import confined
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen

LEAD_IN = 0.4
SENTENCE_GAP = 0.35
CHAPTER_GAP = 1.1
TAIL = 0.8
WORDS_PER_SECOND = 2.5
TARGET_LUFS = -16.0
CEILING_DBTP = -1.5
# LaTeX, markup and symbols a voice reads as characters (or skips): say them in words.
UNSPEAKABLE = re.compile(r"\\[(\[a-zA-Z]|[_^{}$|]|[∑∏∫√≤≥≠≈→←↔⇒⇔∀∃¬∧∨⊨⊢∈∉⊂⊆∪∩×÷·∞]")
META = re.compile(
    r"\bprepared\b|\b(?:this|the) (?:track|audio(?: note)?s?|recording|episode)\b", re.I
)
PRONOUN_START = re.compile(r"^(?:this|that|these|those|it|they|he|she)\b", re.I)


def audio(root: Path, relative: str = "") -> Path:
    return confined(root, f"audio/{relative}" if relative else "audio")


class SourceRef(Frozen):
    kind: SourceKind = "unit"
    unit: Key

    @property
    def target(self) -> str:
        return AudioUnit(kind=self.kind, unit=self.unit, semantic_sha256="0" * 64).target


class Cover(Frozen):
    kind: SourceKind = "unit"
    unit: Key
    locator: Locator
    mode: Literal["spoken", "study_required"] = "spoken"
    reason: Annotated[str, Field(min_length=1, max_length=600)] | None = None


class ScriptChapter(Frozen):
    key: Key
    title: Short
    covers: tuple[Cover, ...] = Field(min_length=1, max_length=200)
    sentences: tuple[Sentence, ...] = Field(min_length=1, max_length=300)


class CategoryScript(Frozen):
    """One published track: its sources, voice profile and chapters of spoken sentences."""

    schema_version: Literal[1] = 1
    key: Key
    stem: Stem
    title: Short
    voice: Key
    units: tuple[SourceRef, ...] = Field(min_length=1, max_length=300)
    chapters: tuple[ScriptChapter, ...] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def consistent(self) -> "CategoryScript":
        keys = [chapter.key for chapter in self.chapters]
        if len(keys) != len(set(keys)):
            raise ValueError("Chapter keys must be unique.")
        targets = [unit.target for unit in self.units]
        if len(targets) != len(set(targets)):
            raise ValueError("Category units must be unique.")
        for chapter in self.chapters:
            for cover in chapter.covers:
                AudioCoverage(**cover.model_dump(), section=chapter.key, chapter=chapter.key)
                if (
                    AudioUnit(kind=cover.kind, unit=cover.unit, semantic_sha256="0" * 64).target
                    not in targets
                ):
                    raise ValueError(
                        f"Chapter {chapter.key} covers a unit the category does not list."
                    )
        return self


def _documents(root: Path) -> tuple[StudyContent | None, ExamContent | None]:
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.content.exam_data import read_exam
    from tum_mcp.course.content.store import present

    study = read_content(root) if present(root, "study") else None
    return study, read_exam(root)


def sources(root: Path) -> dict:
    from tum_mcp.course.media.video_project import unit_locators

    study, exam = _documents(root)
    result: dict = {"study": [], "exam": {"concepts": [], "patterns": []}}
    for unit in study.units if study else ():
        info = unit_locators(root, unit.key)
        result["study"].append(
            {
                "unit": unit.key,
                "title": unit.title,
                "required": [
                    item["ref"]
                    for item in info["locators"]
                    if item["kind"] in {"block", "objective"}
                ],
                "locators": info["locators"],
            }
        )
    for concept in exam.concepts if exam else ():
        result["exam"]["concepts"].append(
            {
                "unit": concept.key,
                "title": concept.title,
                "topic": concept.topic,
                "locator": {
                    "kind": "concept",
                    "ref": concept.key,
                    "fingerprint": exam_hash(concept),
                },
            }
        )
    for pattern in exam.patterns if exam else ():
        result["exam"]["patterns"].append(
            {
                "unit": pattern.key,
                "title": pattern.title,
                "topic": pattern.topic,
                "steps": len(pattern.workflow),
                "locator": {
                    "kind": "pattern",
                    "ref": pattern.key,
                    "fingerprint": exam_hash(pattern),
                },
            }
        )
    return result


def load_script(root: Path, stem: str) -> CategoryScript:
    script = _read(audio(root, f"categories/{stem}.json"), CategoryScript, limit=2 * 1024**2)
    if script is None:
        raise CampusError(Code.ACTION_REQUIRED, f"Write audio/categories/{stem}.json first.")
    if script.stem != stem:
        raise CampusError(Code.WORKSPACE_CONFLICT, f"Category stem must be '{stem}'.")
    return script


def _current(study: StudyContent | None, exam: ExamContent | None, kind: str, key: str):
    if kind == "unit":
        return next((unit for unit in study.units if unit.key == key), None) if study else None
    return exam_item(exam, kind, key)


def check(root: Path, stem: str) -> dict:
    script = load_script(root, stem)
    study, exam = _documents(root)
    errors: list[str] = []
    warnings: list[str] = []
    covered: dict[str, set[str]] = {unit.target: set() for unit in script.units}
    for unit in script.units:
        if _current(study, exam, unit.kind, unit.unit) is None:
            errors.append(f"source.missing: {unit.target}")
    for chapter in script.chapters:
        for cover in chapter.covers:
            item = _current(study, exam, cover.kind, cover.unit)
            if item is None:
                continue
            actual = (
                locator_fingerprint(item, cover.locator)
                if cover.kind == "unit"
                else exam_hash(item)
            )
            if actual != cover.locator.fingerprint:
                errors.append(
                    f"cover.changed {chapter.key}: {cover.unit}/{cover.locator.ref}; copy the "
                    "current fingerprint from sources after re-reading it"
                )
            covered[
                AudioUnit(kind=cover.kind, unit=cover.unit, semantic_sha256="0" * 64).target
            ].add(cover.locator.ref)
        for index, sentence in enumerate(chapter.sentences, 1):
            if found := UNSPEAKABLE.search(sentence):
                errors.append(
                    f"speech.symbols {chapter.key}/{index}: '{found[0]}' in '{sentence[:80]}'; "
                    "say the mathematics in words"
                )
            if found := META.search(sentence):
                warnings.append(
                    f"speech.meta {chapter.key}/{index}: '{found[0]}' talks about the material, "
                    "not the subject"
                )
            if len(sentence.split()) > 40:
                warnings.append(f"speech.long {chapter.key}/{index}: split sentences over 40 words")
        if PRONOUN_START.search(chapter.sentences[0]):
            warnings.append(
                f"reentry.pronoun {chapter.key}: a chapter opens by naming its subject, "
                "so a listener who skips to it knows what 'it' is"
            )
    for unit in script.units:
        item = _current(study, exam, unit.kind, unit.unit)
        if item is None:
            continue
        required = (
            [f"blocks[{i}]" for i in range(len(item.blocks))] + [o.key for o in item.objectives]
            if unit.kind == "unit"
            else [unit.unit]
        )
        missing = [ref for ref in required if ref not in covered[unit.target]]
        if missing:
            errors.append(f"coverage.missing {unit.target}: " + ", ".join(missing))
    words = sum(len(s.split()) for chapter in script.chapters for s in chapter.sentences)
    return {
        "category": script.key,
        "stem": stem,
        "errors": errors,
        "warnings": warnings,
        "words": words,
        "estimated_minutes": round(words / WORDS_PER_SECOND / 60, 1),
    }


def _voice(root: Path, key: str):
    voice = _read(audio(root, "voice.json"), VoiceFile) or VoiceFile()
    if key not in voice.profiles:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Add voice profile '{key}' to audio/voice.json (tum-mcp audio-notes schema voice).",
        )
    return voice.profiles[key]


def _chunks(root: Path, script: CategoryScript) -> list[dict]:
    tag = voice_tag(script.voice, _voice(root, script.voice))
    folder = audio(root, f".build/{script.stem}/chunks")
    items = []
    for chapter in script.chapters:
        for index, text in enumerate(chapter.sentences, 1):
            name = chunk_name(chapter.key, index, text, tag)
            found = next(
                (
                    folder / f"{name}.{ext}"
                    for ext in AUDIO_EXTENSIONS
                    if (folder / f"{name}.{ext}").is_file()
                ),
                None,
            )
            items.append(
                {
                    "chapter": chapter.key,
                    "sentence": index,
                    "text": text,
                    "name": name,
                    "file": f"audio/.build/{script.stem}/chunks/{name}.wav",
                    "present": found is not None,
                    "path": found,
                }
            )
    return items


def narration(root: Path, stem: str) -> list[dict]:
    return [
        {key: value for key, value in item.items() if key not in {"name", "path"}}
        for item in _chunks(root, load_script(root, stem))
    ]


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(audio(root)).as_posix()


def _file(root: Path, path: Path) -> AudioFile:
    return AudioFile(path=_relative(root, path), sha256=_hash_file(path), size=path.stat().st_size)


def _evidence(root: Path, path: Path, value: dict) -> MediaFile:
    import json

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_write(path, (json.dumps(value, indent=2) + "\n").encode())
    return MediaFile(path=_relative(root, path), sha256=_hash_file(path))


def publish(root: Path, stem: str, teaching_review: Path) -> dict:
    report = check(root, stem)
    if report["errors"]:
        raise CampusError(
            Code.ACTION_REQUIRED, "Fix the category first: " + "; ".join(report["errors"][:8])
        )
    if teaching_review.is_symlink() or not teaching_review.is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Pass the teaching review file you recorded.")
    script = load_script(root, stem)
    profile = _voice(root, script.voice)
    chunks = _chunks(root, script)
    absent = [item["file"] for item in chunks if not item["present"]]
    if absent:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"{len(absent)} narration file(s) are missing; run narration, first: {absent[0]}",
        )
    folder = audio(root, ".build")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        lock = FileLock(str(folder / "audio.lock"), timeout=5)
        lock.acquire()
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Another Audio Notes command is running for this course."
        ) from None
    try:
        return _publish(root, script, profile, chunks, teaching_review)
    finally:
        lock.release()


def _publish(
    root: Path,
    script: CategoryScript,
    profile: VoiceProfile,
    chunks: list[dict],
    teaching_review: Path,
) -> dict:
    from tum_mcp.course.media.video_runtime import call_worker, render_profile
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.review.media_projection import guidance_hash

    study, exam = _documents(root)
    build = audio(root, f".build/{script.stem}")
    measured = call_worker({"action": "measure", "files": [str(item["path"]) for item in chunks]})[
        "durations"
    ]
    plan: list[dict] = []
    timeline: list[dict] = []
    marks: list[dict] = []
    cursor = LEAD_IN
    for chapter in script.chapters:
        start = 0.0 if not marks else max(0.0, cursor - 0.25)
        if marks:
            marks[-1]["end"] = start
        marks.append({"key": chapter.key, "title": chapter.title, "start": start})
        for item in (c for c in chunks if c["chapter"] == chapter.key):
            length = float(measured[str(item["path"])])
            plan.append(
                {
                    "file": str(item["path"]),
                    "start": round(cursor, 4),
                    "end": round(cursor + length, 4),
                }
            )
            timeline.append(
                {
                    "chapter": chapter.key,
                    "sentence": item["sentence"],
                    "text": item["text"],
                    "start": round(cursor, 4),
                    "end": round(cursor + length, 4),
                }
            )
            cursor += length + SENTENCE_GAP
        cursor += CHAPTER_GAP - SENTENCE_GAP
    total = round(cursor - CHAPTER_GAP + TAIL, 4)
    marks[-1]["end"] = total
    course = load_state(root).course
    output = build / "track.m4a"
    result = call_worker(
        {
            "action": "track",
            "audio": plan,
            "total": total,
            "output": str(output),
            "chapters": [
                {"title": m["title"], "start": m["start"], "end": m["end"]} for m in marks
            ],
            "tags": {
                "title": script.title,
                "album": course.title,
                "artist": f"Synthetic narration ({profile.provider} {profile.voice})",
                "comment": "Generated by tum-mcp Audio Notes from the course app.",
            },
        },
        timeout=1800,
    )
    probe = result["probe"]
    problems = []
    if probe["audio_codec"] != "aac" or "m4a" not in probe["container"].split(","):
        problems.append("the track is not AAC in M4A")
    if not probe["decoded_samples"]:
        problems.append("the track does not decode")
    if abs(probe["audio_duration"] - total) > 0.15:
        problems.append(f"duration {probe['audio_duration']} s differs from the planned {total} s")
    if probe["loudness_lufs"] is None or abs(probe["loudness_lufs"] - TARGET_LUFS) > 1:
        problems.append(f"loudness {probe['loudness_lufs']} LUFS is not near {TARGET_LUFS}")
    if probe["true_peak_dbtp"] > CEILING_DBTP:
        problems.append(f"true peak {probe['true_peak_dbtp']} dBTP is above {CEILING_DBTP}")
    if len(probe["chapters"]) != len(marks):
        problems.append("embedded chapters do not match the script")
    if problems:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "The assembled track failed: " + "; ".join(problems)
        )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    targets = {
        "track": audio(root, f"tracks/{script.stem}.m4a"),
        "script": audio(root, f"scripts/{script.stem}.txt"),
        "chapters": audio(root, f"chapters/{script.stem}.json"),
    }
    for path in targets.values():
        if path.exists():
            kept = audio(root, f"archive/{script.stem}-{stamp}/{path.name}")
            kept.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.move(path, kept)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copyfile(output, targets["track"])
    text = [script.title, ""]
    for chapter in script.chapters:
        text += [chapter.title, *chapter.sentences, ""]
    private_write(targets["script"], "\n".join(text).encode())
    chapters = AudioChapters(
        tuple(
            AudioChapter(key=m["key"], title=m["title"], start=m["start"], end=m["end"])
            for m in marks
        )
    )
    private_write(targets["chapters"], chapters.model_dump_json(indent=2).encode() + b"\n")
    evidence = {
        "probe": {
            key: probe[key]
            for key in ("container", "audio_codec", "sample_rate", "channels", "tags")
        },
        "decode": {
            "decoded_samples": probe["decoded_samples"],
            "duration": probe["audio_duration"],
        },
        "loudness": {
            "loudness_lufs": probe["loudness_lufs"],
            "true_peak_dbtp": probe["true_peak_dbtp"],
        },
    }
    files = {
        name: _evidence(root, build / f"{name}.json", value) for name, value in evidence.items()
    }
    _evidence(root, build / "timeline.json", {"total": total, "sentences": timeline})
    track = _file(root, targets["track"])
    validation = AudioValidation(
        artifact_sha256=track.sha256,
        tool=AudioTool(name="tum-mcp media runtime", version=render_profile()),
        duration=probe["audio_duration"],
        codec=probe["audio_codec"],
        container=probe["container"],
        sample_rate=probe["sample_rate"],
        channels=probe["channels"],
        decoded=True,
        loudness_lufs=probe["loudness_lufs"],
        true_peak_dbtp=probe["true_peak_dbtp"],
        probe=files["probe"],
        decode=files["decode"],
        loudness=files["loudness"],
    )
    validation_path = build / "validation.json"
    _write_json(validation_path, validation)
    review_path = build / "teaching-review.md"
    if teaching_review.resolve() != review_path.resolve():
        shutil.copyfile(teaching_review, review_path)
    units = tuple(
        AudioUnit(
            kind=unit.kind,
            unit=unit.unit,
            semantic_sha256=semantic_hash(item) if unit.kind == "unit" else exam_hash(item),
        )
        for unit in script.units
        if (item := _current(study, exam, unit.kind, unit.unit)) is not None
    )
    references = {
        (version.key, version.sha256): version
        for unit in script.units
        for version in _current(study, exam, unit.kind, unit.unit).sources
    }
    coverage = tuple(
        AudioCoverage(**cover.model_dump(), section=chapter.key, chapter=chapter.key)
        for chapter in script.chapters
        for cover in chapter.covers
    )
    base = {
        "key": script.key,
        "stem": script.stem,
        "title": script.title,
        "units": units,
        "category_sha256": category_hash(script.title, units),
        "coverage": coverage,
    }
    receipt = AudioReceipt(
        **base,
        source_references=tuple(references[key] for key in sorted(references)),
        script=_file(root, targets["script"]),
        track=track,
        chapters=_file(root, targets["chapters"]),
        voice=profile,
        chunk_inputs=tuple(
            ChunkInput(key=item["name"], sha256=_hash_file(item["path"])) for item in chunks
        ),
        duration=probe["audio_duration"],
        teaching_review=TeachingReviewFile(
            path=_relative(root, review_path),
            sha256=_hash_file(review_path),
            guidance_sha256=guidance_hash("audio"),
        ),
        validation=MediaFile(
            path=_relative(root, validation_path), sha256=_hash_file(validation_path)
        ),
    )
    manifest = _read(audio(root, "manifest.json"), AudioManifest) or AudioManifest(
        course_key=course.key
    )
    manifest = manifest.model_copy(
        update={"categories": {**manifest.categories, script.key: receipt}}
    )
    plan_record = _read(audio(root, "plan.json"), AudioPlan)
    content_sha = sha256(canonical([semantic_hash(u) for u in study.units] if study else []))
    planned = PlannedAudio(**base, pending="none", voice=profile)
    order = plan_record.category_order if plan_record else ()
    plan_record = AudioPlan(
        course_key=course.key,
        content_sha256=plan_record.content_sha256 if plan_record else content_sha,
        category_order=order if script.key in order else (*order, script.key),
        categories={**(plan_record.categories if plan_record else {}), script.key: planned},
    )
    _write_json(audio(root, "plan.json"), plan_record)
    _write_json(audio(root, "manifest.json"), manifest)
    playlist = ["#EXTM3U"] + [
        f"tracks/{manifest.categories[key].stem}.m4a"
        for key in plan_record.category_order
        if key in manifest.categories
    ]
    private_write(audio(root, "playlist.m3u"), ("\n".join(playlist) + "\n").encode())
    return {
        "category": script.key,
        "track": f"audio/{track.path}",
        "duration": receipt.duration,
        "chapters": [{"title": m["title"], "start": m["start"]} for m in marks],
        "loudness_lufs": probe["loudness_lufs"],
        "true_peak_dbtp": probe["true_peak_dbtp"],
        "warnings": check(root, script.stem)["warnings"],
        "listening": f"run tum-mcp audio-notes listen PROJECT {script.stem}",
    }
