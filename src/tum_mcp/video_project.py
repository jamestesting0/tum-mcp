"""Course-local Video Notes workflow: plans, timing, rendering, receipts and publication."""

import ast
import hashlib
import json
import os
import re
import secrets
import shutil
import time
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
from pathlib import Path

from filelock import FileLock, Timeout
from pydantic import BaseModel, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.study_build import read_content
from tum_mcp.study_content import StudyContent, Unit
from tum_mcp.study_store import confined
from tum_mcp.video_content import (
    ChapterBound,
    ExerciseChapterBound,
    ExerciseReceipt,
    ExerciseStoryboard,
    FileReceipt,
    Locator,
    Manifest,
    Receipt,
    SelectionFile,
    Storyboard,
    StoryboardFile,
    StoryboardReport,
    StyleProfile,
    Timing,
    VideoPlan,
    VoiceFile,
    allocate,
    canonical,
    check_storyboard,
    chunk_name,
    compose_timing,
    estimate_seconds,
    locator_fingerprint,
    now,
    semantic_hash,
    sha256,
    source_key,
    transcript,
    unit_revision,
    voice_tag,
)
from tum_mcp.video_lint import LintReport, lint
from tum_mcp.video_media import (
    QUALITY,
    CheckReport,
    Probe,
    Quality,
    captions,
    chapters,
    check_media,
)
from tum_mcp.video_sources import VideoSource, VideoSources, check_exercise, read_sources
from tum_mcp.video_style import staged_bytes

ROOT = "videos"
AUDIO_EXTENSIONS = ("wav", "mp3", "m4a", "flac", "ogg")
BUILD_BUDGET = 5 * 1024**3
MANAGED_START = "<!-- tum-mcp:video-notes:start -->"
MANAGED_END = "<!-- tum-mcp:video-notes:end -->"
WORDS_PER_SECOND_RANGE = (1.0, 5.5)
RUN_ID = re.compile(r"^r-[0-9a-f]{8}$")


def videos(root: Path, relative: str = "") -> Path:
    return confined(root, f"{ROOT}/{relative}" if relative else ROOT)


def _read[M: BaseModel](path: Path, model: type[M], limit: int = 8 * 1024**2) -> M | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise CampusError(Code.WORKSPACE_CONFLICT, f"{path.name} needs local review.")
    try:
        return model.model_validate_json(path.read_bytes())
    except ValidationError as error:
        where = ", ".join(".".join(map(str, e["loc"])) for e in error.errors()[:5])
        raise CampusError(
            Code.INVALID_RESPONSE, f"Invalid {path.name} at: {where or 'document'}."
        ) from None


def _write_json(path: Path, value: BaseModel) -> bytes:
    data = value.model_dump_json(indent=2).encode() + b"\n"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_write(path, data)
    return data


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _content(root: Path) -> tuple[StudyContent, str]:
    from tum_mcp.course_app_paths import app_path

    content = read_content(root)
    return content, _hash_file(app_path(root, "content.json"))


def _unit(content: StudyContent, key: str) -> Unit:
    unit = next((item for item in content.units if item.key == key), None)
    if unit is None:
        raise CampusError(Code.STALE_RESULT, f"Prepared content no longer has unit '{key}'.")
    return unit


def load_plan(root: Path) -> VideoPlan | None:
    return _read(videos(root, "plan.json"), VideoPlan)


def load_manifest(root: Path) -> Manifest | None:
    return _read(videos(root, "manifest.json"), Manifest)


def load_style(root: Path) -> StyleProfile:
    return _read(videos(root, "style.json"), StyleProfile) or StyleProfile()


def load_voice(root: Path) -> VoiceFile:
    return _read(videos(root, "voice.json"), VoiceFile) or VoiceFile()


def stored_storyboard(root: Path, stem: str) -> tuple[Storyboard | ExerciseStoryboard, bytes]:
    path = videos(root, f"storyboards/{stem}.json")
    record = _read(path, StoryboardFile, limit=2 * 1024**2)
    if record is None:
        raise CampusError(Code.ACTION_REQUIRED, f"Write videos/storyboards/{stem}.json first.")
    model = record.root
    if model.video != stem:
        raise CampusError(Code.WORKSPACE_CONFLICT, f"Storyboard video must be '{stem}'.")
    return model, path.read_bytes()


def _planned(root: Path, stem: str) -> str:
    plan = load_plan(root)
    entry = next((item for item in plan.videos if item.stem == stem), None) if plan else None
    if entry is None:
        raise CampusError(Code.ACTION_REQUIRED, f"'{stem}' is not a planned video; run plan.")
    return source_key(entry)


def work(root: Path, stem: str, relative: str = "") -> Path:
    base = f".build/{stem}"
    return videos(root, f"{base}/{relative}" if relative else base)


@contextmanager
def locked(root: Path) -> Iterator[None]:
    folder = videos(root, ".build")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with FileLock(str(folder / "video.lock"), timeout=5):
            _recover(root)
            yield
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Another Video Notes command is running for this course."
        ) from None


def _run_folder(root: Path, stem: str, run: str) -> Path:
    if not RUN_ID.fullmatch(run):
        raise CampusError(Code.INVALID_RESPONSE, f"'{run}' is not a render run id (r-xxxxxxxx).")
    return confined(work(root, stem, "runs"), run)


@contextmanager
def _run_guard(folder: Path) -> Iterator[None]:
    """Held for a whole render; taken only while the course lock is held."""
    lock = FileLock(str(folder / "run.lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, f"Run {folder.name} is still rendering."
        ) from None
    try:
        yield
    finally:
        lock.release()


def _idle(folder: Path) -> bool:
    try:
        with _run_guard(folder):
            return True
    except CampusError:
        return False


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _scaffold(root: Path) -> None:
    folder = videos(root)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    ignore = videos(root, ".gitignore")
    if not ignore.exists():
        private_write(ignore, b".build/\narchive/\n")
    if not videos(root, "style.json").exists():
        _write_json(videos(root, "style.json"), StyleProfile())
    if not videos(root, "voice.json").exists():
        _write_json(videos(root, "voice.json"), VoiceFile())


def unrecognized(root: Path) -> bool:
    folder = videos(root)
    if not folder.exists():
        return False
    known = {"plan.json", "manifest.json", "style.json", "voice.json", ".build"}
    return not any((folder / name).exists() for name in known) and any(folder.iterdir())


def _guard_layout(root: Path) -> None:
    if unrecognized(root):
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "videos/ already holds files that Video Notes did not create; review or move "
            "them first. Nothing was changed.",
        )


def plan(root: Path, selection_file: Path) -> VideoPlan:
    _guard_layout(root)
    selection = _read(selection_file, SelectionFile, limit=1024**2)
    if selection is None:
        raise CampusError(Code.ACTION_REQUIRED, "The selection file does not exist.")
    sources = read_sources(root)
    for item in (*selection.units, *selection.exercises):
        sources.get(source_key(item))
    with locked(root):
        _scaffold(root)
        previous = load_plan(root)
        if previous is not None and previous.course_key != sources.course_key:
            raise CampusError(Code.SCOPE_DENIED, "videos/plan.json belongs to another course.")
        manifest = load_manifest(root)
        if manifest is not None and manifest.course_key != sources.course_key:
            raise CampusError(Code.SCOPE_DENIED, "videos/manifest.json belongs to another course.")
        receipts = manifest.videos if manifest else {}
        published = {source_key(receipt): stem for stem, receipt in receipts.items()}
        try:
            entries = allocate(
                previous,
                (*selection.units, *selection.exercises),
                sources.study,
                frozenset(receipts),
                published,
                sources.exercises,
            )
        except ValueError as error:
            raise CampusError(Code.INVALID_RESPONSE, str(error)) from None
        result = VideoPlan(
            course_key=sources.course_key,
            content_sha256=sources.content_sha256,
            exercises_sha256=sources.exercises_sha256,
            videos=entries,
        )
        _write_json(videos(root, "plan.json"), result)
        _write_documents(root)
        return result


def check(root: Path, stem: str) -> StoryboardReport:
    identity = _planned(root, stem)
    storyboard, _ = stored_storyboard(root, stem)
    sources = read_sources(root)
    source = sources.get(identity)
    plan_ = load_plan(root)
    if plan_ is not None and plan_.course_key != sources.course_key:
        raise CampusError(Code.SCOPE_DENIED, "Video plan belongs to another course.")
    match storyboard:
        case Storyboard():
            if sources.study is None:
                raise CampusError(Code.ACTION_REQUIRED, "Prepare the selected Study unit first.")
            report = check_storyboard(storyboard, sources.study)
        case ExerciseStoryboard():
            report = check_exercise(storyboard, source)
    errors = list(report.errors)
    if source_key(storyboard) != identity:
        errors.insert(0, f"plan.source: the plan assigns '{stem}' to '{identity}'")
    report = report.model_copy(update={"errors": tuple(errors)})
    if not report.errors:
        with locked(root):
            # Working copy; videos/narration/ holds only published transcripts.
            path = work(root, stem, "transcript.txt")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            private_write(path, transcript(storyboard).encode())
    return report


def unit_locators(root: Path, unit_key: str) -> dict:
    content, _ = _content(root)
    unit = _unit(content, unit_key)
    items: list[dict] = [{"kind": "summary", "ref": "summary", "preview": unit.summary[:120]}]
    for index, block in enumerate(unit.blocks):
        items.append(
            {
                "kind": "block",
                "ref": f"blocks[{index}]",
                "preview": f"{block.kind}: {block.title or 'untitled'}",
            }
        )
    items += [{"kind": "objective", "ref": o.key, "preview": o.text[:120]} for o in unit.objectives]
    items += [
        {"kind": "flashcard", "ref": c.key, "preview": c.front[:120]} for c in unit.flashcards
    ]
    items += [{"kind": "question", "ref": q.key, "preview": q.prompt[:120]} for q in unit.questions]
    for item in items:
        item["fingerprint"] = locator_fingerprint(
            unit, Locator(kind=item["kind"], ref=item["ref"], fingerprint="0" * 64)
        )
    formulas = [
        {"ref": f"blocks[{index}]", "latex": block.latex}
        for index, block in enumerate(unit.blocks)
        if block.kind == "formula" and block.latex
    ]
    return {
        "unit": unit.key,
        "title": unit.title,
        "unit_hash": semantic_hash(unit),
        "revision": unit_revision(unit),
        "locators": items,
        "formulas": formulas,
    }


def exercise_locators(root: Path, key: str) -> dict:
    from tum_mcp.exercise_content import Exercise

    source = read_sources(root).get(f"exercises/{key}")
    match source.data:
        case Exercise() as exercise:
            locators = source.locators()
            formulas = []
            for locator in locators:
                value = source.resolve(locator)
                blocks = value.blocks if locator.kind == "answer" else (value,)
                for block in blocks:
                    if getattr(block, "kind", None) == "formula":
                        formulas.append({"ref": locator.ref, "latex": block.latex})
            return {
                "exercise": source.exercise.model_dump(mode="json"),
                "title": exercise.title,
                "exercise_hash": source.teaching_hash,
                "revision": source.revision,
                "parts": exercise.parts,
                "answers": [a.model_dump(mode="json") for a in locators if a.kind == "answer"],
                "origin": exercise.solution.origin,
                "source_references": [s.model_dump(mode="json") for s in exercise.sources],
                "locators": [a.model_dump(mode="json") for a in locators],
                "formulas": formulas,
            }
        case Unit():
            raise CampusError(Code.INVALID_RESPONSE, "Expected an Exercise source.")


def _ready_storyboard(
    root: Path,
    stem: str,
) -> tuple[Storyboard | ExerciseStoryboard, bytes, VideoSources]:
    report = check(root, stem)
    if report.errors:
        raise CampusError(
            Code.INVALID_RESPONSE, "Fix the storyboard first: " + "; ".join(report.errors[:5])
        )
    storyboard, data = stored_storyboard(root, stem)
    return storyboard, data, read_sources(root)


def narration(root: Path, stem: str, profile: str) -> list[dict]:
    storyboard, _ = stored_storyboard(root, stem)
    voice = load_voice(root)
    if profile not in voice.profiles:
        raise CampusError(
            Code.ACTION_REQUIRED, f"Add voice profile '{profile}' to videos/voice.json."
        )
    audio = work(root, stem, "audio")
    tag = voice_tag(profile, voice.profiles[profile])
    items = []
    for beat in storyboard.beats():
        for index, text in enumerate(beat.narration, 1):
            name = chunk_name(beat.key, index, text, tag)
            found = [ext for ext in AUDIO_EXTENSIONS if (audio / f"{name}.{ext}").is_file()]
            items.append(
                {
                    "beat": beat.key,
                    "sentence": index,
                    "text": text,
                    "file": f"videos/.build/{stem}/audio/{name}.wav",
                    "accepted_extensions": list(AUDIO_EXTENSIONS),
                    "present": bool(found),
                }
            )
    return items


def timing(
    root: Path, stem: str, *, profile: str | None, silent: bool, executable: Path | None = None
) -> Timing:
    from tum_mcp.video_runtime import call_worker

    storyboard, data, _ = _ready_storyboard(root, stem)
    durations: dict[str, tuple[float, str | None]] = {}
    if silent:
        voice = "silent"
        for beat in storyboard.beats():
            for index, text in enumerate(beat.narration, 1):
                durations[f"{beat.key}/{index}"] = (
                    max(0.8, round(len(text.split()) / 2.33, 3)),
                    None,
                )
    else:
        if profile is None:
            raise CampusError(Code.ACTION_REQUIRED, "Pass --profile, or --silent for a draft.")
        profiles = load_voice(root).profiles
        if profile not in profiles:
            raise CampusError(Code.ACTION_REQUIRED, f"Unknown voice profile '{profile}'.")
        voice = voice_tag(profile, profiles[profile])
        audio = work(root, stem, "audio")
        files: dict[str, Path] = {}
        missing = []
        for beat in storyboard.beats():
            for index, text in enumerate(beat.narration, 1):
                name = chunk_name(beat.key, index, text, voice)
                found = [audio / f"{name}.{ext}" for ext in AUDIO_EXTENSIONS]
                present = [path for path in found if path.is_file()]
                if len(present) != 1:
                    missing.append(f"{name}.*" if not present else f"{name} (several formats)")
                    continue
                files[f"{beat.key}/{index}"] = present[0]
        if missing:
            raise CampusError(
                Code.ACTION_REQUIRED,
                f"{len(missing)} narration chunk(s) missing or ambiguous, e.g. {missing[0]}; "
                "run narration to list them.",
            )
        if files:
            result = call_worker(
                {"action": "measure", "files": [str(path) for path in files.values()]},
                executable=executable,
                timeout=900,
            )
            if not result.get("ok"):
                raise CampusError(Code.INVALID_RESPONSE, f"Measuring audio failed: {result}")
            measured = result["durations"]
            problems = []
            for key, path in files.items():
                seconds = float(measured[str(path)])
                beat, index = key.split("/")
                text = next(b for b in storyboard.beats() if b.key == beat).narration[
                    int(index) - 1
                ]
                rate = len(text.split()) / seconds if seconds > 0 else float("inf")
                low, high = WORDS_PER_SECOND_RANGE
                if seconds <= 0.2 or (len(text.split()) >= 4 and not low <= rate <= high):
                    problems.append(f"{path.name}: {seconds:.2f}s for {len(text.split())} words")
                durations[key] = (seconds, path.name)
            if problems:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    "Narration audio looks truncated or garbled; regenerate: "
                    + "; ".join(problems[:5]),
                )
    result_timing = compose_timing(storyboard, sha256(data), voice, durations)
    with locked(root):
        _write_json(work(root, stem, "timing.json"), result_timing)
    return result_timing


def load_timing(root: Path, stem: str, storyboard_bytes: bytes) -> Timing:
    value = _read(work(root, stem, "timing.json"), Timing)
    if value is None:
        raise CampusError(Code.ACTION_REQUIRED, "Run timing for this video first.")
    if value.storyboard_sha256 != sha256(storyboard_bytes):
        raise CampusError(Code.STALE_RESULT, "The storyboard changed; run timing again.")
    if not value.silent:
        key = value.voice.split("@", 1)[0]
        profile = load_voice(root).profiles.get(key)
        if profile is None or voice_tag(key, profile) != value.voice:
            raise CampusError(Code.STALE_RESULT, "The voice profile changed; run timing again.")
    return value


def _class_sources(source: str) -> tuple[str, dict[str, str]]:
    tree = ast.parse(source)
    shared = []
    classes: dict[str, str] = {}
    for node in tree.body:
        segment = ast.get_source_segment(source, node) or ""
        if isinstance(node, ast.ClassDef):
            classes[node.name] = segment
        else:
            shared.append(segment)
    return "\n".join(shared), classes


def _asset_digest(root: Path, source: str) -> str:
    names = {
        node.args[0].value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr == "asset"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    items = []
    for name in sorted(names):
        path = videos(root, f"assets/{name}")
        if not path.is_file():
            raise CampusError(Code.ACTION_REQUIRED, f"Missing referenced video asset '{name}'.")
        items.append((name, _hash_file(path)))
    return sha256(canonical(items))


def _new_run() -> str:
    return "r-" + secrets.token_hex(4)


def render(
    root: Path,
    stem: str,
    *,
    quality: Quality,
    jobs: int,
    max_minutes: float | None,
    run: str | None,
) -> dict:
    from tum_mcp.video_runtime import render_profile, status

    if _size(videos(root, ".build")) > BUILD_BUDGET:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "videos/.build exceeds its 5 GiB budget; run tum-mcp video-notes prune first.",
        )
    runtime = status()
    if not runtime.installed:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Install the render runtime first: tum-mcp video-notes runtime install"
            + (f" ({'; '.join(runtime.commands)})" if runtime.commands else ""),
        )
    storyboard, story_bytes, _ = _ready_storyboard(root, stem)
    timings = load_timing(root, stem, story_bytes)
    scene_path = videos(root, f"scenes/{stem}/chapters.py")
    if not scene_path.is_file() or scene_path.stat().st_size > 512 * 1024:
        raise CampusError(Code.ACTION_REQUIRED, f"Write videos/scenes/{stem}/chapters.py first.")
    # Hash the bytes publish and inspect hash; read_text would normalize CRLF (Windows).
    scene_bytes = scene_path.read_bytes()
    source = scene_bytes.decode("utf-8")
    report = lint(source, storyboard)
    if not report.ok:
        return {
            "stem": stem,
            "ok": False,
            "lint": list(report.errors),
            "warnings": list(report.warnings),
        }
    style = load_style(root)
    style_bytes = staged_bytes(style)
    runtime_profile = render_profile()
    inputs = {
        "storyboard": sha256(story_bytes),
        "scene": sha256(scene_bytes),
        "style": sha256(style_bytes),
        "timing": sha256(timings.model_dump_json().encode()),
        "voice": sha256(timings.voice.encode()),
        "assets": _asset_digest(root, source),
        "profile": runtime_profile,
        "quality": quality,
    }
    guard = ExitStack()
    with locked(root):
        runs = work(root, stem, "runs")
        if run is not None:
            folder = _run_folder(root, stem, run)
            pending = _pending(folder)
            if pending is None or pending.get("inputs") != inputs:
                raise CampusError(
                    Code.STALE_RESULT, f"Run {run} has different inputs; start a new run."
                )
        else:
            run = _new_run()
            folder = confined(runs, run)
            folder.mkdir(mode=0o700, parents=True)
            _stage_run(root, folder, storyboard, story_bytes, timings, style_bytes, source)
            _save_pending(
                folder,
                {"run": run, "stem": stem, "inputs": inputs, "stage": "render", "chapters": {}},
            )
        guard.enter_context(_run_guard(folder))
    with guard:
        return _render_run(
            root,
            stem,
            storyboard,
            timings,
            source,
            report,
            inputs,
            folder,
            run,
            quality,
            jobs,
            max_minutes,
            runtime_profile,
        )


def _render_run(
    root: Path,
    stem: str,
    storyboard: Storyboard | ExerciseStoryboard,
    timings: Timing,
    source: str,
    report: LintReport,
    inputs: dict,
    folder: Path,
    run: str,
    quality: Quality,
    jobs: int,
    max_minutes: float | None,
    runtime_profile: str,
) -> dict:
    from tum_mcp.video_runtime import call_worker, python_path

    shared, classes = _class_sources(source)
    cache = work(root, stem, f"cache/{runtime_profile[-25:].replace('-', '')}/{quality}")
    deadline = time.monotonic() + max_minutes * 60 if max_minutes else None
    pending = _pending(folder) or {}
    done: dict[str, dict] = dict(pending.get("chapters", {}))
    todo = [chapter for chapter in storyboard.chapters if chapter.key not in done]
    results: list[dict] = []
    stopped = False
    executable = python_path()
    fps = QUALITY[quality]["fps"]

    def chapter_key(key: str) -> str:
        spec = next(c for c in storyboard.chapters if c.key == key)
        beat_times = [b.model_dump(mode="json") for b in timings.beats if b.chapter == key]
        return sha256(
            canonical(
                [
                    shared,
                    classes.get(key.upper(), ""),
                    spec.model_dump(mode="json"),
                    beat_times,
                    inputs["style"],
                    inputs["assets"],
                    runtime_profile,
                    quality,
                ]
            )
        )[:16]

    def one(key: str) -> dict:
        record = cache / f"{key}-{chapter_key(key)}.json"
        video = record.with_suffix(".mp4")
        target = folder / "chapters" / f"{key}.mp4"
        target.parent.mkdir(exist_ok=True)
        if record.is_file() and video.is_file():
            cached = json.loads(record.read_text(encoding="utf-8"))
            shutil.copyfile(video, target)
            return {**cached, "cached": True}
        result = call_worker(
            {
                "action": "render",
                "run": str(folder),
                "chapter": key,
                "quality": quality,
                "media": str(cache / "media" / key),
            },
            executable=executable,
            timeout=1200 if quality == "draft" else 3600,
            log=folder / "logs" / f"{key}.log",
        )
        if result.get("ok") and target.is_file():
            cache.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, video)
            kept = {k: result[k] for k in ("chapter", "ok", "frames", "duration", "layout")}
            private_write(record, json.dumps(kept).encode())
        return result

    with ThreadPoolExecutor(max_workers=max(1, min(jobs, 8))) as pool:
        futures: dict[Future, str] = {}
        queue = list(todo)
        while queue or futures:
            while queue and len(futures) < max(1, jobs):
                if deadline is not None and time.monotonic() > deadline:
                    stopped = True
                    queue.clear()
                    break
                chapter = queue.pop(0)
                futures[pool.submit(one, chapter.key)] = chapter.key
            if not futures:
                break
            finished, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in finished:
                key = futures.pop(future)
                try:
                    result = future.result()
                except (CampusError, OSError) as error:
                    message = getattr(error, "message", None) or f"{type(error).__name__}: {error}"
                    result = {"chapter": key, "ok": False, "error": message}
                results.append(result)
                if result.get("ok"):
                    done[key] = {
                        "frames": int(result["frames"]),
                        "layout": result.get("layout", []),
                        "cached": bool(result.get("cached")),
                    }
                    current = _pending(folder) or {}
                    current["chapters"] = done
                    _save_pending(folder, current)
    failures = [r for r in results if not r.get("ok")]
    summary: dict = {
        "stem": stem,
        "run": run,
        "quality": quality,
        "chapters": {k: {"frames": v["frames"], "cached": v["cached"]} for k, v in done.items()},
        "warnings": list(report.warnings),
        "failures": [{"chapter": r.get("chapter"), "error": r.get("error")} for r in failures],
    }
    if failures or stopped or len(done) < len(storyboard.chapters):
        summary["ok"] = False
        summary["resume"] = f"tum-mcp video-notes render PROJECT {stem} --{quality} --run {run}"
        if stopped:
            summary["stopped"] = "time budget reached at a chapter boundary"
        return summary
    order = [chapter.key for chapter in storyboard.chapters]
    frame_counts = [done[key]["frames"] for key in order]
    layout = [issue for key in order for issue in done[key]["layout"]]
    bounds, clock = [], 0
    for chapter, frames in zip(storyboard.chapters, frame_counts, strict=True):
        bounds.append(
            ChapterBound(
                key=chapter.key,
                title=chapter.title,
                start=round(clock / fps, 3),
                end=round((clock + frames) / fps, 3),
            )
        )
        clock += frames
    audio_plan = [
        {"file": str(work(root, stem, f"audio/{cue.audio}")), "start": cue.start, "end": cue.end}
        for beat in timings.beats
        for cue in beat.cues
        if cue.audio
    ]
    first = timings.beats[0]
    poster_at = first.start + first.duration - 0.1
    if isinstance(storyboard, ExerciseStoryboard) and first.cues:
        # The first sentence establishes the problem; later work may reveal its answer.
        cue = first.cues[0]
        poster_at = cue.start + min(0.8, (cue.end - cue.start) / 2)
    assembled = call_worker(
        {
            "action": "assemble",
            "quality": quality,
            "chapters": [
                {"file": str(folder / "chapters" / f"{key}.mp4"), "frames": frames}
                for key, frames in zip(order, frame_counts, strict=True)
            ],
            "audio": [] if timings.silent else audio_plan,
            "output": str(folder / "track.mp4"),
            "poster": str(folder / "poster.jpg"),
            "poster_at": max(0.0, min(poster_at, clock / fps - 0.1)),
        },
        executable=executable,
        timeout=3600,
        log=folder / "logs" / "assemble.log",
    )
    if not assembled.get("ok"):
        summary.update(
            ok=False, failures=[{"chapter": "assemble", "error": assembled.get("error")}]
        )
        return summary
    probe = Probe.model_validate(assembled["probe"])
    captions_text = captions(timings)
    chapters_text = chapters(tuple(bounds))
    private_write(folder / "captions.vtt", captions_text.encode())
    private_write(folder / "chapters.vtt", chapters_text.encode())
    private_write(
        folder / "chapters.json",
        json.dumps([bound.model_dump(mode="json") for bound in bounds], indent=2).encode(),
    )
    private_write(folder / "transcript.txt", transcript(storyboard).encode())
    private_write(folder / "probe.json", probe.model_dump_json(indent=2).encode())
    sheets = _sheets(folder, storyboard, timings, bounds, executable, fps)
    result = _check_run(folder, quality, timings, probe, layout)
    current = _pending(folder) or {}
    current.update(
        stage="checked", ok=result.ok, bounds=[b.model_dump(mode="json") for b in bounds]
    )
    _save_pending(folder, current)
    seconds, _ = estimate_seconds(storyboard)
    summary.update(
        ok=result.ok,
        track=_display(root, folder / "track.mp4"),
        duration=probe.video_duration,
        estimated=seconds,
        check={"passed": list(result.passed), "failed": list(result.failed)},
        layout=layout,
        sheets=[_display(root, sheet) for sheet in sheets],
        formulas=[
            {
                "beat": beat.key,
                "key": item.key,
                "source_latex": item.source_latex,
                "typst": item.typst,
            }
            for beat in storyboard.beats()
            for item in beat.on_screen
            if item.kind == "math"
        ],
    )
    return summary


def _display(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _stage_run(
    root: Path,
    folder: Path,
    storyboard: Storyboard | ExerciseStoryboard,
    story_bytes: bytes,
    timings: Timing,
    style_bytes: bytes,
    source: str,
) -> None:
    private_write(folder / "storyboard.json", story_bytes)
    private_write(folder / "timing.json", timings.model_dump_json().encode())
    private_write(folder / "style.json", style_bytes)
    private_write(folder / "chapters.py", source.encode())
    assets = videos(root, "assets")
    target = folder / "assets"
    target.mkdir(mode=0o700)
    if assets.is_dir():
        for path in assets.iterdir():
            if path.is_file() and path.suffix == ".svg" and not path.is_symlink():
                if path.stat().st_size > 2 * 1024**2:
                    raise CampusError(Code.INVALID_RESPONSE, f"Asset {path.name} exceeds 2 MiB.")
                shutil.copyfile(path, target / path.name)


def _pending(folder: Path) -> dict | None:
    path = folder / "pending.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _save_pending(folder: Path, value: dict) -> None:
    private_write(folder / "pending.json", json.dumps(value, indent=2).encode())


def _sheets(
    folder: Path,
    storyboard: Storyboard | ExerciseStoryboard,
    timings: Timing,
    bounds: list[ChapterBound],
    executable: Path,
    fps: float,
) -> list[Path]:
    from tum_mcp.video_runtime import call_worker

    output = []
    (folder / "sheets").mkdir(exist_ok=True)
    for chapter, bound in zip(storyboard.chapters, bounds, strict=True):
        beats = [beat for beat in timings.beats if beat.chapter == chapter.key]
        offset = bound.start - beats[0].start
        by_frame: dict[int, list[str]] = {}
        last_frame = max(round(bound.start * fps), round(bound.end * fps) - 1)
        for beat in beats:
            first = min(
                last_frame, max(round(bound.start * fps), round((beat.start + offset) * fps))
            )
            last = min(
                last_frame, max(first, round((beat.start + beat.duration + offset) * fps) - 1)
            )
            seen: set[int] = set()
            for phase, frame in (("entry", first), ("middle", (first + last) // 2), ("exit", last)):
                if frame not in seen:
                    seen.add(frame)
                    moment = frame / fps
                    by_frame.setdefault(frame, []).append(
                        f"{chapter.key} {beat.key} {moment:.3f}s {phase}"
                    )
        samples = [(frame / fps, "; ".join(labels)) for frame, labels in sorted(by_frame.items())]
        for page, start in enumerate(range(0, len(samples), 12), 1):
            group = samples[start : start + 12]
            sheet = folder / "sheets" / f"{chapter.key}-{page:02d}.png"
            result = call_worker(
                {
                    "action": "frames",
                    "file": str(folder / "track.mp4"),
                    "times": [moment for moment, _ in group],
                    "labels": [label for _, label in group],
                    "output": str(sheet),
                },
                executable=executable,
                timeout=600,
            )
            if result.get("ok") and sheet.is_file():
                output.append(sheet)
    return output


def _check_run(
    folder: Path, quality: Quality, timings: Timing, probe: Probe, layout: list[dict]
) -> CheckReport:
    report = check_media(
        probe,
        quality=quality,
        timing=timings,
        track=folder / "track.mp4",
        captions_text=(folder / "captions.vtt").read_text(encoding="utf-8"),
        chapters_text=(folder / "chapters.vtt").read_text(encoding="utf-8"),
        poster=folder / "poster.jpg",
    )
    problems = [
        f"layout {issue['chapter']}/{issue['beat']}: {issue['rule']} {issue['detail']}"
        for issue in layout
        if not issue["rule"].endswith(".waived")
    ]
    failed = (*report.failed, *problems)
    passed = report.passed if problems else (*report.passed, "layout.clear")
    result = report.model_copy(update={"failed": failed, "passed": passed})
    private_write(folder / "check.json", result.model_dump_json(indent=2).encode())
    return result


def recheck(root: Path, stem: str, run: str) -> CheckReport:
    folder = _run_folder(root, stem, run)
    pending = _pending(folder)
    probe = _read(folder / "probe.json", Probe)
    if pending is None or probe is None:
        raise CampusError(Code.ACTION_REQUIRED, f"Run {run} has not been assembled yet.")
    timings = _read(folder / "timing.json", Timing)
    if timings is None:
        raise CampusError(Code.WORKSPACE_CONFLICT, f"Run {run} lost its timing record.")
    layout = [issue for item in pending.get("chapters", {}).values() for issue in item["layout"]]
    return _check_run(folder, pending["inputs"]["quality"], timings, probe, layout)


def frames(root: Path, stem: str, run: str, times: list[float]) -> str:
    from tum_mcp.video_runtime import call_worker

    folder = _run_folder(root, stem, run)
    track = folder / "track.mp4"
    if not track.is_file():
        raise CampusError(Code.ACTION_REQUIRED, f"Run {run} has no assembled track.")
    output = folder / "sheets" / f"at-{secrets.token_hex(3)}.png"
    output.parent.mkdir(exist_ok=True)
    result = call_worker(
        {
            "action": "frames",
            "file": str(track),
            "times": times,
            "labels": [f"{t:.2f}s" for t in times],
            "output": str(output),
        },
        timeout=600,
    )
    if not result.get("ok"):
        raise CampusError(Code.INVALID_RESPONSE, f"Frame extraction failed: {result.get('error')}")
    return _display(root, output)


def _current_inputs(root: Path, stem: str) -> dict[str, str]:
    _, story_bytes = stored_storyboard(root, stem)
    timings = load_timing(root, stem, story_bytes)
    scene = videos(root, f"scenes/{stem}/chapters.py").read_bytes()
    return {
        "storyboard": sha256(story_bytes),
        "scene": sha256(scene),
        "style": sha256(staged_bytes(load_style(root))),
        "timing": sha256(timings.model_dump_json().encode()),
        "voice": sha256(timings.voice.encode()),
        "assets": _asset_digest(root, scene.decode("utf-8")),
    }


def _journal(root: Path) -> Path:
    return videos(root, ".build/publish-journal.json")


def _recover(root: Path) -> None:
    """Undo a publication interrupted before its manifest was written."""
    journal = _journal(root)
    if not journal.is_file():
        return
    try:
        entries = json.loads(journal.read_text(encoding="utf-8"))
        for item in entries["files"]:
            target = videos(root, item["path"])
            backup = item.get("backup")
            if backup:
                shutil.copyfile(videos(root, backup), target)
            elif target.exists():
                target.unlink()
    except (OSError, ValueError, KeyError, TypeError, CampusError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "An interrupted publication could not be undone automatically; review "
            "videos/.build/publish-journal.json and the archive/ backups it lists.",
        ) from None
    journal.unlink()


def publish(
    root: Path, stem: str, run: str, *, teaching_review: Path, visual_review: str
) -> Receipt | ExerciseReceipt:
    from tum_mcp.media_projection import guidance_hash

    identity = _planned(root, stem)
    storyboard, _, sources_ = _ready_storyboard(root, stem)
    source_ = sources_.get(identity)
    if teaching_review.is_symlink() or not teaching_review.is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Pass the teaching review file you recorded.")
    review = teaching_review.read_bytes()
    if not review.strip() or len(review) > 256 * 1024:
        raise CampusError(Code.INVALID_RESPONSE, "The teaching review must be 1 byte to 256 KiB.")
    with locked(root):
        folder = _run_folder(root, stem, run)
        if folder.is_dir() and not _idle(folder):
            raise CampusError(Code.WORKSPACE_CONFLICT, f"Run {run} is still rendering.")
        pending = _pending(folder)
        if pending is None or pending.get("stage") != "checked":
            raise CampusError(Code.ACTION_REQUIRED, f"Run {run} has not been rendered and checked.")
        if pending["inputs"]["quality"] != "final":
            raise CampusError(Code.ACTION_REQUIRED, "Only final-quality runs can be published.")
        result = _read(folder / "check.json", CheckReport)
        if result is None or not result.ok:
            raise CampusError(Code.ACTION_REQUIRED, f"Run {run} has failing checks.")
        if not result.narrated:
            raise CampusError(
                Code.ACTION_REQUIRED, "Silent drafts are never published; narration is pending."
            )
        current = _current_inputs(root, stem)
        current["profile"] = pending["inputs"]["profile"]
        current["quality"] = "final"
        if current != pending["inputs"]:
            raise CampusError(
                Code.STALE_RESULT,
                "Inputs changed after this run was rendered; render again before publishing.",
            )
        timings = _read(folder / "timing.json", Timing)
        assert timings is not None  # noqa: S101 - staged with the run and validated above
        bounds = tuple(ChapterBound.model_validate(item) for item in pending["bounds"])
        probe = _read(folder / "probe.json", Probe)
        assert probe is not None  # noqa: S101 - written before the checked stage
        sources = {
            "track": (folder / "track.mp4", f"tracks/{stem}.mp4"),
            "captions": (folder / "captions.vtt", f"captions/{stem}.vtt"),
            "chapters": (folder / "chapters.vtt", f"chapters/{stem}.vtt"),
            "chapter_index": (folder / "chapters.json", f"chapters/{stem}.json"),
            "poster": (folder / "poster.jpg", f"posters/{stem}.jpg"),
            "transcript": (folder / "transcript.txt", f"narration/{stem}.txt"),
        }
        review_path = f"reviews/{stem}-{run}.md"
        stamp_ = now().strftime("%Y%m%dT%H%M%SZ")
        archive = f"archive/{stamp_}-{run}"
        journal_files = []
        for _, relative in sources.values():
            target = videos(root, relative)
            if target.exists():
                backup = f"{archive}/{relative}"
                videos(root, backup).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(target, videos(root, backup))
                journal_files.append({"path": relative, "backup": backup})
            else:
                journal_files.append({"path": relative, "backup": None})
        manifest = load_manifest(root) or Manifest(course_key=sources_.course_key)
        if manifest.course_key != sources_.course_key:
            raise CampusError(Code.SCOPE_DENIED, "Video manifest belongs to another course.")
        if stem in manifest.videos:
            previous = videos(root, f"{archive}/receipt.json")
            previous.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            private_write(previous, manifest.videos[stem].model_dump_json(indent=2).encode())
        private_write(_journal(root), json.dumps({"stem": stem, "files": journal_files}).encode())
        files = {}
        for name, (source, relative) in sources.items():
            target = videos(root, relative)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            staged = target.with_name(f".write-{secrets.token_hex(4)}")
            shutil.copyfile(source, staged)
            staged.chmod(0o600)
            os.replace(staged, target)
            files[name] = FileReceipt(
                path=relative, sha256=_hash_file(target), size=target.stat().st_size
            )
        review_target = videos(root, review_path)
        review_target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        private_write(review_target, review)
        fields = dict(
            stem=stem,
            title=storyboard.title,
            language=storyboard.language,
            made_for_revision=source_.revision,
            inputs={
                key: current[key] for key in ("storyboard", "scene", "style", "timing", "voice")
            },
            render_profile=current["profile"],
            narrated=True,
            duration=probe.video_duration,
            files=files,
            checks=result.passed,
            teaching_review=review_path,
            visual_review="performed" if visual_review == "performed" else "not_performed",
            run=run,
            published_at=now(),
            voice_profile_key=timings.voice.split("@", 1)[0],
            voice_profile=load_voice(root).profiles[timings.voice.split("@", 1)[0]],
            assets_sha256=current["assets"],
            source_references=source_.source_references,
            beats=timings.beats,
            visuals=tuple(
                f"{chapter.key}/{beat.key}/{key}"
                for chapter in storyboard.chapters
                for beat in chapter.beats
                for key in (tuple(item.key for item in beat.on_screen) or ("scene",))
            ),
            guidance_sha256=guidance_hash("video"),
            teaching_review_sha256=sha256(review),
        )
        match storyboard:
            case Storyboard():
                receipt = Receipt(
                    **fields,
                    unit=storyboard.unit,
                    unit_hash=source_.teaching_hash,
                    chapters=bounds,
                    objectives=storyboard.objectives,
                )
            case ExerciseStoryboard():
                used = {
                    locator.ref: locator
                    for beat in storyboard.beats()
                    for locator in beat.locators
                    if locator.kind == "prerequisite"
                }
                receipt = ExerciseReceipt(
                    **fields,
                    exercise=storyboard.exercise,
                    exercise_hash=source_.teaching_hash,
                    answers=storyboard.answers,
                    prerequisites=tuple(used.values()),
                    solution_origin=source_.data.solution.origin,
                    chapters=tuple(
                        ExerciseChapterBound(**bound.model_dump(), answer=chapter.answer)
                        for bound, chapter in zip(bounds, storyboard.chapters, strict=True)
                    ),
                )
        videos_map = {
            key: value for key, value in manifest.videos.items() if source_key(value) != identity
        }
        videos_map[stem] = receipt
        updated = manifest.model_copy(update={"videos": videos_map})
        _write_json(videos(root, "manifest.json"), updated)
        _journal(root).unlink()
        pending["stage"] = "published"
        _save_pending(folder, pending)
        _write_documents(root)
        return receipt


def acknowledge(root: Path, stem: str, review_file: Path) -> Receipt | ExerciseReceipt:
    sources = read_sources(root)
    review = review_file.read_bytes() if review_file.is_file() else b""
    if not review.strip() or len(review) > 256 * 1024:
        raise CampusError(Code.ACTION_REQUIRED, "Pass a non-empty coverage review file.")
    with locked(root):
        manifest = load_manifest(root)
        if manifest is None or stem not in manifest.videos:
            raise CampusError(Code.ACTION_REQUIRED, f"'{stem}' has no published video.")
        receipt = manifest.videos[stem]
        if manifest.course_key != sources.course_key:
            raise CampusError(Code.SCOPE_DENIED, "Video manifest belongs to another course.")
        source = sources.get(source_key(receipt))
        storyboard, story_bytes = stored_storyboard(root, stem)
        if source_key(storyboard) != source.identity:
            raise CampusError(Code.STALE_RESULT, "The storyboard source changed; render instead.")
        if sha256(story_bytes) != receipt.inputs["storyboard"]:
            raise CampusError(
                Code.STALE_RESULT, "The storyboard changed since publication; render instead."
            )
        match storyboard:
            case Storyboard():
                unit = _unit(sources.study, storyboard.unit)
                changed = [
                    f"{beat.key} {locator.kind} {locator.ref}"
                    for beat in storyboard.beats()
                    for locator in beat.locators
                    if locator_fingerprint(unit, locator) != locator.fingerprint
                ]
                if any(o not in {x.key for x in unit.objectives} for o in storyboard.objectives):
                    changed.append("objectives changed")
                identity_update = {"unit_hash": source.teaching_hash}
                receipt_update = identity_update
            case ExerciseStoryboard():
                changed = list(check_exercise(storyboard, source).errors)
                identity_update = {"exercise_hash": source.teaching_hash}
                receipt_update = {
                    **identity_update,
                    "source_references": source.source_references,
                    "solution_origin": source.data.solution.origin,
                }
        if changed:
            raise CampusError(
                Code.STALE_RESULT,
                "Teaching used by this video changed (" + ", ".join(changed[:5]) + "); "
                "revise the storyboard and render again.",
            )
        refreshed = storyboard.model_copy(update=identity_update)
        refreshed_bytes = _write_json(videos(root, f"storyboards/{stem}.json"), refreshed)
        timing_path = work(root, stem, "timing.json")
        timings = _read(timing_path, Timing)
        inputs = dict(receipt.inputs)
        inputs["storyboard"] = sha256(refreshed_bytes)
        if timings is not None and timings.storyboard_sha256 == receipt.inputs["storyboard"]:
            moved = timings.model_copy(update={"storyboard_sha256": sha256(refreshed_bytes)})
            _write_json(timing_path, moved)
            inputs["timing"] = sha256(moved.model_dump_json().encode())
        review_path = f"reviews/{stem}-ack-{now().strftime('%Y%m%dT%H%M%SZ')}.md"
        target = videos(root, review_path)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        private_write(target, review)
        updated = receipt.model_copy(
            update={
                "made_for_revision": source.revision,
                **receipt_update,
                "inputs": inputs,
                "reviews": (*receipt.reviews, review_path),
            }
        )
        videos_map = dict(manifest.videos)
        videos_map[stem] = updated
        _write_json(
            videos(root, "manifest.json"), manifest.model_copy(update={"videos": videos_map})
        )
        _write_documents(root)
        return updated


def inspect(root: Path, *, stem: str | None = None, verify: bool = False) -> dict:
    from tum_mcp.video_runtime import python_path, render_profile

    sources = read_sources(root)
    plan_ = load_plan(root)
    manifest = load_manifest(root)
    if any(
        record is not None and record.course_key != sources.course_key
        for record in (plan_, manifest)
    ):
        raise CampusError(Code.SCOPE_DENIED, "Video records belong to another course.")
    receipts = manifest.videos if manifest else {}
    rows = []
    exercise_rows = []
    entries = {source_key(item): item for item in plan_.videos} if plan_ else {}
    by_source = {source_key(receipt): receipt for receipt in receipts.values()}
    for identity, source in sources.items.items():
        entry = entries.get(identity)
        receipt = by_source.get(identity)
        name = entry.stem if entry else receipt.stem if receipt else None
        if stem is not None and name != stem:
            continue
        row: dict = {
            **(
                {"exercise": source.exercise.model_dump(mode="json")}
                if source.exercise
                else {"unit": source.data.key}
            ),
            "source": identity,
            "title": source.data.title,
            "decision": entry.decision if entry else "unplanned",
            "stem": name,
        }
        if entry and entry.decision == "text-first":
            row["reason"] = entry.reason
        if name:
            row.update(_video_state(root, name, source, receipts.get(name), verify))
        (exercise_rows if source.exercise else rows).append(row)
    known = set(sources.items)
    orphans = sorted(
        {
            source_key(item)
            for item in (plan_.videos if plan_ else ())
            if source_key(item) not in known
        }
        | {source_key(r) for r in receipts.values() if source_key(r) not in known}
    )
    return {
        "course_key": sources.course_key,
        "content_sha256": sources.content_sha256,
        "exercises_sha256": sources.exercises_sha256,
        "plan_current": bool(
            plan_
            and plan_.content_sha256 == sources.content_sha256
            and plan_.exercises_sha256 == sources.exercises_sha256
        ),
        "unrecognized_videos_folder": unrecognized(root),
        "interrupted_publication": _journal(root).exists() if videos(root).exists() else False,
        "runtime": {"profile": render_profile(), "present": python_path().is_file()},
        "build_bytes": _size(videos(root, ".build")) if videos(root).exists() else 0,
        "build_budget_bytes": BUILD_BUDGET,
        "units": rows,
        "exercises": exercise_rows,
        "orphaned_units": [
            key.removeprefix("study/") for key in orphans if key.startswith("study/")
        ],
        "orphaned_exercises": [
            key.removeprefix("exercises/") for key in orphans if key.startswith("exercises/")
        ],
    }


def _video_state(
    root: Path,
    stem: str,
    source: VideoSource,
    receipt: Receipt | ExerciseReceipt | None,
    verify: bool,
) -> dict:
    state: dict = {}
    path = videos(root, f"storyboards/{stem}.json")
    story_bytes = path.read_bytes() if path.is_file() else None
    if story_bytes is None:
        state["storyboard"] = "missing"
    else:
        try:
            storyboard = StoryboardFile.model_validate_json(story_bytes).root
            match storyboard:
                case Storyboard():
                    content_hash = storyboard.unit_hash
                case ExerciseStoryboard():
                    content_hash = storyboard.exercise_hash
            state["storyboard"] = (
                "current"
                if (
                    source_key(storyboard) == source.identity
                    and content_hash == source.teaching_hash
                )
                else "stale"
            )
        except ValidationError:
            state["storyboard"] = "invalid"
    timing_ = work(root, stem, "timing.json")
    if timing_.is_file() and story_bytes is not None:
        try:
            value = Timing.model_validate_json(timing_.read_bytes())
            state["timing"] = (
                "current" if value.storyboard_sha256 == sha256(story_bytes) else "stale"
            )
            state["narrated"] = not value.silent
        except ValidationError:
            state["timing"] = "invalid"
    else:
        state["timing"] = "missing"
    runs = work(root, stem, "runs")
    state["runs"] = (
        sorted(
            (
                {
                    "run": folder.name,
                    "stage": (_pending(folder) or {}).get("stage", "unknown"),
                    "quality": (_pending(folder) or {}).get("inputs", {}).get("quality"),
                }
                for folder in runs.iterdir()
                if folder.is_dir()
            ),
            key=lambda item: item["run"],
        )
        if runs.is_dir()
        else []
    )
    if receipt is None:
        state["published"] = "none"
        return state
    files_ok = True
    for item in receipt.files.values():
        target = videos(root, item.path)
        if not target.is_file() or target.stat().st_size != item.size:
            files_ok = False
        elif verify and _hash_file(target) != item.sha256:
            files_ok = False
    edited = story_bytes is not None and sha256(story_bytes) != receipt.inputs["storyboard"]
    scene = videos(root, f"scenes/{stem}/chapters.py")
    if scene.is_file() and sha256(scene.read_bytes()) != receipt.inputs["scene"]:
        edited = True
    match receipt:
        case Receipt():
            teaching_changed = receipt.unit_hash != source.teaching_hash
            provenance_changed = False
        case ExerciseReceipt():
            teaching_changed = receipt.exercise_hash != source.teaching_hash or any(
                source.locator_hash(locator) != locator.fingerprint
                for locator in receipt.prerequisites
            )
            provenance_changed = (
                receipt.source_references != source.source_references
                or receipt.solution_origin != source.data.solution.origin
            )
    if not files_ok:
        state["published"] = "missing_or_changed_files"
    elif teaching_changed:
        state["published"] = "teaching_changed"
    elif source.stale or provenance_changed:
        state["published"] = "source_changed"
    elif receipt.inputs["style"] != sha256(staged_bytes(load_style(root))):
        state["published"] = "style_changed"
    elif receipt.made_for_revision != source.revision:
        state["published"] = "revision_changed_acknowledge_or_render"
    else:
        state["published"] = "current"
    state["edited_since_publication"] = edited
    state["duration"] = receipt.duration
    return state


def prune(root: Path, *, keep: int) -> dict:
    from tum_mcp.video_runtime import render_profile

    current = render_profile()[-25:].replace("-", "")
    freed = 0
    removed = []
    with locked(root):
        build = videos(root, ".build")
        for stem_dir in sorted(p for p in build.iterdir() if p.is_dir()):
            runs = stem_dir / "runs"
            if runs.is_dir():
                # Snapshot ages first: probing a run's lock touches its folder.
                aged = sorted((p.stat().st_mtime, p) for p in runs.iterdir() if p.is_dir())
                idle = [folder for _, folder in aged if _idle(folder)]
                for folder in idle[: max(0, len(idle) - keep)]:
                    freed += _size(folder)
                    shutil.rmtree(folder)
                    removed.append(_display(root, folder))
            cache = stem_dir / "cache"
            if cache.is_dir():
                for folder in cache.iterdir():
                    if folder.is_dir() and folder.name != current:
                        freed += _size(folder)
                        shutil.rmtree(folder)
                        removed.append(_display(root, folder))
    return {"removed": removed, "freed_bytes": freed, "build_bytes": _size(videos(root, ".build"))}


def _managed(path: Path, block: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    wrapped = f"{MANAGED_START}\n{block.rstrip()}\n{MANAGED_END}"
    if existing.count(MANAGED_START) == 1 and existing.count(MANAGED_END) == 1:
        start = existing.index(MANAGED_START)
        end = existing.index(MANAGED_END) + len(MANAGED_END)
        if start < end:
            updated = existing[:start] + wrapped + existing[end:]
        else:
            raise CampusError(Code.WORKSPACE_CONFLICT, f"{path.name} markers need review.")
    elif MANAGED_START in existing or MANAGED_END in existing:
        raise CampusError(Code.WORKSPACE_CONFLICT, f"{path.name} markers need review.")
    else:
        updated = (existing.rstrip() + "\n\n" if existing.strip() else "") + wrapped + "\n"
    if updated != existing:
        private_write(path, updated.encode())


def _write_documents(root: Path) -> None:
    inventory = read_sources(root)
    plan_ = load_plan(root)
    manifest = load_manifest(root)
    receipts = manifest.videos if manifest else {}
    voice = load_voice(root)
    order = {identity: index for index, identity in enumerate(inventory.items)}
    published = sorted(receipts.values(), key=lambda r: order.get(source_key(r), 10**6))
    total = sum(r.duration for r in published)
    readme = [
        "# Video Notes",
        "",
        "Narrated videos adapt prepared Study concepts or solve selected prepared Exercises.",
        "Open the local course app with `tum-mcp study`: concept videos are in Content;",
        "walkthroughs stay inside Solution disclosures. Hosted sites never include media.",
        "Each MP4 has a fixed theme; it does not switch with the app's theme.",
        "",
        f"Published videos: {len(published)}, total {total / 60:.1f} min.",
        "",
    ]
    for receipt in published:
        readme.append(
            f"- **{receipt.title}** ({receipt.duration / 60:.1f} min): `tracks/{receipt.stem}.mp4`,"
            f" captions `captions/{receipt.stem}.vtt`, transcript `narration/{receipt.stem}.txt`"
        )
        for bound in receipt.chapters:
            readme.append(f"  - {_clock(bound.start)} {bound.title}")
    if voice.profiles:
        readme += ["", "Narrators (synthetic voices):"]
        readme += [
            f"- `{key}`: {p.provider} via {p.route}, voice {p.voice}, model {p.model}"
            for key, p in sorted(voice.profiles.items())
        ]
    readme += [
        "",
        "Update after the course content changes: ask your agent to update the video notes.",
        "`tum-mcp video-notes inspect PROJECT` lists changed, stale and pending videos.",
    ]
    _managed(videos(root, "README.md"), "\n".join(readme))
    coverage = ["# Coverage", ""]
    entries = {source_key(item): item for item in plan_.videos} if plan_ else {}
    by_source = {source_key(r): r for r in receipts.values()}
    for identity, source in inventory.items.items():
        entry = entries.get(identity)
        receipt = by_source.get(identity)
        title = source.data.title
        if entry is None:
            coverage.append(f"- {title}: not planned")
        elif entry.decision == "text-first":
            coverage.append(f"- {title}: text-first ({entry.reason})")
        elif receipt is None:
            coverage.append(f"- {title}: planned as `{entry.stem}`, not yet published")
        else:
            state = _video_state(root, receipt.stem, source, receipt, False)
            match receipt:
                case Receipt():
                    covered = f"objectives in video: {', '.join(receipt.objectives)}"
                case ExerciseReceipt():
                    covered = f"answers in video: {', '.join(a.ref for a in receipt.answers)}"
            coverage.append(
                f"- {title}: `{receipt.stem}` ({state['published']}); {covered}"
                + ("; visual review not performed" if receipt.visual_review != "performed" else "")
            )
    _managed(videos(root, "COVERAGE.md"), "\n".join(coverage))
    sources = [
        "# Sources",
        "",
        f"Prepared course: `{inventory.course_key}`.",
        f"Study SHA-256: `{inventory.content_sha256}`; "
        f"Exercises SHA-256: `{inventory.exercises_sha256}`.",
        "",
    ]
    for receipt in published:
        source = inventory.items.get(source_key(receipt))
        if source is not None:
            cited = ", ".join(f"{s.key} ({s.sha256[:12]})" for s in source.source_references)
            sources.append(f"- `{receipt.stem}` <- `{source.identity}`: {cited}")
    _managed(videos(root, "SOURCES.md"), "\n".join(sources))
    playlist = ["#EXTM3U"]
    for receipt in published:
        playlist += [
            f"#EXTINF:{round(receipt.duration)},{receipt.title}",
            f"tracks/{receipt.stem}.mp4",
        ]
    private_write(videos(root, "playlist.m3u"), ("\n".join(playlist) + "\n").encode())


def _clock(seconds: float) -> str:
    minutes, whole = divmod(int(seconds), 60)
    return f"{minutes}:{whole:02d}"


def preview_index(root: Path) -> dict:
    """Published videos whose files are present, for the local app only. Never raises."""
    try:
        manifest = _read(videos(root, "manifest.json"), Manifest, limit=1024**2)
        inventory = read_sources(root) if manifest else None
        if manifest is not None and manifest.course_key != inventory.course_key:
            raise CampusError(Code.SCOPE_DENIED, "Video manifest belongs to another course.")
    except (CampusError, OSError):
        return {"videos": {}, "exercises": {}}
    entries: dict[str, dict] = {}
    exercise_entries: dict[str, dict] = {}
    for receipt in manifest.videos.values() if manifest else ():
        try:
            present = all(
                (path := videos(root, item.path)).is_file()
                and not path.is_symlink()
                and path.stat().st_size == item.size
                for item in receipt.files.values()
            )
        except (CampusError, OSError):
            present = False
        if not present:
            continue
        entry = {
            "title": receipt.title,
            "language": receipt.language,
            "duration": receipt.duration,
            "narrated": receipt.narrated,
            "madeForRevision": receipt.made_for_revision,
            "track": f"videos/{receipt.files['track'].path}",
            "captions": f"videos/{receipt.files['captions'].path}",
            "poster": f"videos/{receipt.files['poster'].path}",
            "transcript": f"videos/{receipt.files['transcript'].path}",
            "chapters": [
                {"title": bound.title, "start": bound.start} for bound in receipt.chapters
            ],
        }
        match receipt:
            case Receipt():
                entries[receipt.unit] = entry
            case ExerciseReceipt():
                source = inventory.items.get(source_key(receipt))
                entry["sourceStale"] = (
                    source is None
                    or source.stale
                    or source.teaching_hash != receipt.exercise_hash
                    or any(source.locator_hash(p) != p.fingerprint for p in receipt.prerequisites)
                    or source.source_references != receipt.source_references
                    or source.data.solution.origin != receipt.solution_origin
                )
                exercise_entries[receipt.exercise.key] = entry
    return {"videos": entries, "exercises": exercise_entries}


def install_demo(root: Path, example: Path) -> Receipt:
    """Install the synthetic, unnarrated demo video for the component preview unit."""
    _guard_layout(root)
    content, _ = _content(root)
    unit = _unit(content, "components")
    stem = "01_reusable-components"
    names = {
        "track": f"tracks/{stem}.mp4",
        "captions": f"captions/{stem}.vtt",
        "chapters": f"chapters/{stem}.vtt",
        "chapter_index": f"chapters/{stem}.json",
        "poster": f"posters/{stem}.jpg",
        "transcript": f"narration/{stem}.txt",
    }
    with locked(root):
        files = {}
        for name, relative in names.items():
            desired = (example / relative).read_bytes()
            target = videos(root, relative)
            if target.exists() and target.read_bytes() != desired:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Edited demo video files were preserved."
                )
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            private_write(target, desired)
            files[name] = FileReceipt(path=relative, sha256=sha256(desired), size=len(desired))
        bounds = tuple(
            ChapterBound.model_validate(item)
            for item in json.loads((example / names["chapter_index"]).read_text(encoding="utf-8"))
        )
        receipt = Receipt(
            stem=stem,
            unit=unit.key,
            title=unit.title,
            language="en",
            made_for_revision=unit_revision(unit),
            unit_hash=semantic_hash(unit),
            inputs={key: "0" * 64 for key in ("storyboard", "scene", "style", "timing", "voice")},
            render_profile="synthetic-demo",
            narrated=False,
            duration=bounds[-1].end,
            chapters=bounds,
            files=files,
            objectives=tuple(item.key for item in unit.objectives),
            checks=("synthetic demo; not a teaching example",),
            teaching_review="none (synthetic demo)",
            visual_review="not_performed",
            run="r-00000000",
            published_at=now(),
        )
        manifest = load_manifest(root) or Manifest(course_key=content.course_key)
        if manifest.course_key != content.course_key:
            raise CampusError(Code.SCOPE_DENIED, "videos/manifest.json belongs to another course.")
        updated = manifest.model_copy(update={"videos": {**manifest.videos, stem: receipt}})
        _write_json(videos(root, "manifest.json"), updated)
        return receipt


def schemas() -> dict[str, type[BaseModel]]:
    return {
        "storyboard": StoryboardFile,
        "selection": SelectionFile,
        "style": StyleProfile,
        "voice": VoiceFile,
        "manifest": Manifest,
        "timing": Timing,
    }
