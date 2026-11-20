"""Machine listening for published narration: speech recognition aligned with the script and
its planned timing. It checks what was said and when, not how natural the voice sounds."""

import hashlib
import json
import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Final, NotRequired, TypedDict

from pydantic import Field, ValidationError

from tum_mcp.course.media.inventory import MediaItem
from tum_mcp.course.media.video_content import canonical, sha256
from tum_mcp.course.project.models import Digest
from tum_mcp.course.project.store import confined
from tum_mcp.course.review.media import covers_duration
from tum_mcp.course.review.media_projection import file_hash
from tum_mcp.course.review.models import MediaEvidence
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen

METHOD_VERSION: Final = 2
WINDOW = 590.0
STEP = 580.0
MATCH_FLOOR = 0.8
OFFSET_LIMIT = 0.75
GAP = 3
PACE = (110, 200)
NEGATIONS = {"not", "no", "never", "cannot", "without", "none", "neither", "nor", "unless"}
ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
SIGN_OR_NUMBER = (
    NEGATIONS
    | set(ONES)
    | set(TENS[2:])
    | {
        "minus",
        "negative",
        "plus",
        "positive",
        "point",
        "hundred",
        "thousand",
        "million",
        "billion",
    }
)


class TimedWord(TypedDict):
    word: str
    start: float
    end: float


class ExpectedSentence(TypedDict):
    key: str
    text: str
    start: float
    end: float


class WordEdit(TypedDict):
    operation: str
    expected: list[str]
    heard: list[str]
    start: float | None
    end: float | None


class AlignedSentence(ExpectedSentence):
    heard: str
    match: float
    missing: list[str]
    gap: int
    offset: float | None
    spoken_words: int
    spoken_seconds: float
    critical_edits: list[WordEdit]
    rechecked: NotRequired[bool]


class ListeningCheck(TypedDict):
    match: float
    words_per_minute: int
    flags: list[str]
    sentence_flags: dict[str, list[str]]
    track_flags: list[str]


class ListeningReceipt(Frozen):
    evidence: MediaEvidence
    publication_sha256: Digest
    dispositions: dict[str, str] = Field(default_factory=dict)


class ListeningReport(Frozen, extra="ignore"):
    item: str
    artifact_sha256: Digest
    duration: float = Field(gt=0, allow_inf_nan=False)
    method_version: int | None = None
    flags: list[str]
    sentence_flags: dict[str, list[str]] | None = None
    track_flags: list[str] | None = None


def _report_path(item: str) -> str:
    return f".tum-mcp/media-review/{item.replace('/', '-')}-listening.json"


def _receipt_path(root: Path, relative: str) -> Path:
    return confined(root, relative.removesuffix(".json") + ".receipt.json")


def _read_report(
    root: Path, item: str, artifact: str, publication: str, duration: float, tolerance: float
) -> tuple[ListeningReport, ListeningReceipt]:
    relative = _report_path(item)
    path = confined(root, relative)
    try:
        data = path.read_bytes()
    except FileNotFoundError as error:
        raise CampusError(Code.ACTION_REQUIRED, "Listening report is missing.") from error
    try:
        report = ListeningReport.model_validate_json(data)
    except ValidationError as error:
        raise CampusError(
            Code.INVALID_RESPONSE, "Listening report is corrupt. Run listen again."
        ) from error
    if report.method_version != METHOD_VERSION:
        raise CampusError(Code.ACTION_REQUIRED, "Listening method changed. Run listen again.")
    if report.item != item or report.artifact_sha256 != artifact:
        raise CampusError(Code.ACTION_REQUIRED, "Listening report belongs to a different artifact.")
    try:
        receipt = ListeningReceipt.model_validate_json(_receipt_path(root, relative).read_bytes())
    except (FileNotFoundError, ValidationError) as error:
        raise CampusError(
            Code.ACTION_REQUIRED, "Listening receipt is missing or corrupt. Run listen again."
        ) from error
    evidence = receipt.evidence
    if (
        evidence.path != relative
        or evidence.kind != "listening"
        or evidence.sha256 != sha256(data)
        or evidence.artifact_sha256 != artifact
    ):
        raise CampusError(Code.ACTION_REQUIRED, "Listening report changed. Run listen again.")
    if receipt.publication_sha256 != publication:
        raise CampusError(
            Code.ACTION_REQUIRED, "Published narration receipt changed. Run listen again."
        )
    if (
        abs(report.duration - duration) > tolerance
        or not covers_duration(evidence.intervals, duration, tolerance)
        or any(interval.end > duration + tolerance for interval in evidence.intervals)
    ):
        raise CampusError(
            Code.ACTION_REQUIRED, "Listening intervals do not cover the published track."
        )
    if report.sentence_flags is None or report.track_flags is None:
        raise CampusError(Code.INVALID_RESPONSE, "Listening report is missing flag details.")
    return report, receipt


def verify_listening(root: Path, item: MediaItem) -> str:
    """Require full current evidence with every sentence flag addressed."""
    if item.publication_sha256 is None:
        raise CampusError(Code.ACTION_REQUIRED, "Published narration receipt is missing.")
    report, receipt = _read_report(
        root,
        item.item,
        item.artifact_sha256,
        item.publication_sha256,
        item.duration,
        1 / 30 if item.modality == "video" else 0.05,
    )
    reasons = [
        flag
        for key, flags in (report.sentence_flags or {}).items()
        if not receipt.dispositions.get(key, "").strip()
        for flag in flags
    ]
    reasons.extend(report.track_flags or [])
    if reasons:
        raise CampusError(
            Code.ACTION_REQUIRED, f"Unresolved listening flags: {'; '.join(reasons)}."
        )
    return sha256(canonical(receipt.model_dump(mode="json")))


def _dispose(
    root: Path,
    item: str,
    artifact: str,
    publication: str,
    duration: float,
    tolerance: float,
    entries: tuple[str, ...],
) -> dict:
    """Record author reasons against the already inspected, unchanged report."""
    report, receipt = _read_report(root, item, artifact, publication, duration, tolerance)
    flagged = report.sentence_flags or {}
    reasons = dict(receipt.dispositions)
    supplied: set[str] = set()
    for entry in entries:
        key, _, reason = entry.partition("=")
        if key not in flagged:
            raise CampusError(Code.ACTION_REQUIRED, f"Unknown flagged sentence: {key}.")
        if not reason.strip():
            raise CampusError(Code.ACTION_REQUIRED, f"Provide a reason for sentence {key}.")
        if key in supplied:
            raise CampusError(Code.ACTION_REQUIRED, f"Give one reason for sentence {key}.")
        supplied.add(key)
        reasons[key] = reason.strip()
    updated = receipt.model_copy(update={"dispositions": reasons})
    private_write(
        _receipt_path(root, receipt.evidence.path), updated.model_dump_json(indent=2).encode()
    )
    return {
        "item": item,
        "flags": report.flags,
        "dispositions": reasons,
        "report": receipt.evidence.path,
        "evidence": [receipt.evidence.model_dump(mode="json", exclude_defaults=True)],
    }


def _integer(value: int) -> list[str]:
    if value < 20:
        return [ONES[value]]
    if value < 100:
        return [TENS[value // 10]] + ([ONES[value % 10]] if value % 10 else [])
    if value < 1000:
        rest = _integer(value % 100) if value % 100 else []
        return [ONES[value // 100], "hundred", *rest]
    if value < 10000:
        # Four digits read as a year: 1956 "nineteen fifty six", 2005 "two thousand five".
        if 2000 <= value < 2010:
            return ["two", "thousand", *([ONES[value % 10]] if value % 10 else [])]
        tail = _integer(value % 100) if value % 100 else ["hundred"]
        return [*_integer(value // 100), *tail]
    return [str(value)]


def _token_spans(text: str) -> list[tuple[str, int, int]]:
    result: list[tuple[str, int, int]] = []
    for match in re.finditer(
        r"[+−-]?(?:\d+(?:(?:\s+\.\s*|\.)\d+)?|\.\d+)|[A-Z]?[a-z]+(?:['’][a-z]+)?|[A-Z]+",
        text,
    ):
        raw = match.group().lower().replace("’", "'")
        if raw[0] in "+−-." or raw[0].isdigit():
            sign = {"-": ["minus"], "−": ["minus"], "+": ["plus"]}.get(raw[0], [])
            whole, _, fraction = "".join(raw.split()).lstrip("+−-").partition(".")
            words = [*sign, *_integer(int(whole or "0"))]
            if fraction:
                words += ["point", *(ONES[int(digit)] for digit in fraction)]
        elif raw.endswith("n't"):
            base = raw[:-3]
            words = [{"ca": "can", "wo": "will", "sha": "shall"}.get(base, base), "not"]
        elif raw == "cannot":
            words = ["can", "not"]
        else:
            words = [raw.replace("'", "")]
        result.extend((word, match.start(), match.end()) for word in words)
    return result


def tokens(text: str) -> list[str]:
    """Lowercase spoken words; digits become the words a narrator says for them."""
    return [word for word, _, _ in _token_spans(text)]


def align(expected: list[ExpectedSentence], words: list[TimedWord]) -> list[AlignedSentence]:
    result: list[AlignedSentence] = []
    for index, sentence in enumerate(expected):
        lower, upper = sentence["start"] - 0.35, sentence["end"] + 0.35
        if index:
            lower = max(lower, (expected[index - 1]["end"] + sentence["start"]) / 2)
        if index + 1 < len(expected):
            upper = min(upper, (sentence["end"] + expected[index + 1]["start"]) / 2)
        heard = [word for word in words if lower <= (word["start"] + word["end"]) / 2 < upper]
        want = tokens(sentence["text"])
        text = " ".join(word["word"].strip() for word in heard)
        ends: list[int] = []
        cursor = 0
        for word in heard:
            cursor += len(word["word"].strip())
            ends.append(cursor)
            cursor += 1
        got: list[str] = []
        timings: list[tuple[float, float]] = []
        for word, start, end in _token_spans(text):
            got.append(word)
            timings.append(
                (heard[bisect_right(ends, start)]["start"], heard[bisect_left(ends, end)]["end"])
            )
        matcher = SequenceMatcher(None, want, got, autojunk=False)
        missing: list[str] = []
        edits: list[WordEdit] = []
        gap = 0
        for operation, a, b, c, d in matcher.get_opcodes():
            if operation == "equal":
                continue
            removed, inserted = want[a:b], got[c:d]
            missing.extend(removed)
            gap = max(gap, b - a)
            if any(word in SIGN_OR_NUMBER or word.isdecimal() for word in (*removed, *inserted)):
                start = timings[c][0] if c < len(timings) else timings[-1][1] if timings else None
                end = timings[d - 1][1] if d > c else start
                edits.append(
                    {
                        "operation": operation,
                        "expected": removed,
                        "heard": inserted,
                        "start": start,
                        "end": end,
                    }
                )
        result.append(
            {
                **sentence,
                "heard": text,
                "match": round(1 - len(missing) / len(want), 3) if want else 1.0,
                "missing": missing,
                "gap": gap,
                "critical_edits": edits,
                "offset": round(heard[0]["start"] - sentence["start"], 2) if heard else None,
                "spoken_words": len(got),
                "spoken_seconds": round(heard[-1]["end"] - heard[0]["start"], 2) if heard else 0.0,
            }
        )
    return result


def judge(aligned: list[AlignedSentence], words: list[TimedWord]) -> ListeningCheck:
    sentence_flags: dict[str, list[str]] = {}
    for item in aligned:
        flags: list[str] = []
        if item["match"] < MATCH_FLOOR:
            flags.append(f"unclear {item['key']}: heard '{item['heard'][:120]}'")
        elif item["gap"] >= GAP:
            flags.append(f"dropped {item['key']}: {item['gap']} words in a row not heard")
        for edit in item["critical_edits"]:
            removed, inserted = ", ".join(edit["expected"]), ", ".join(edit["heard"])
            match edit["operation"]:
                case "delete":
                    flags.append(f"missing {item['key']}: {removed}")
                case "insert":
                    flags.append(f"added {item['key']}: {inserted}")
                case _:
                    flags.append(f"substituted {item['key']}: {removed} → {inserted}")
        if item["offset"] is not None and abs(item["offset"]) > OFFSET_LIMIT:
            flags.append(f"timing {item['key']}: speech starts {item['offset']:+.2f} s from plan")
        if flags:
            sentence_flags[item["key"]] = flags
    track_flags: list[str] = []
    planned = [(a["end"], b["start"]) for a, b in zip(aligned, aligned[1:], strict=False)]
    for before, after in zip(words, words[1:], strict=False):
        gap = after["start"] - before["end"]
        if gap > 2.0 and not any(
            a - 0.5 <= before["end"] and after["start"] <= b + 0.5 for a, b in planned
        ):
            track_flags.append(f"silence {before['end']:.1f}-{after['start']:.1f} s")
    spoken = sum(item["spoken_seconds"] for item in aligned)
    pace = round(60 * sum(item["spoken_words"] for item in aligned) / spoken) if spoken else 0
    if spoken and not PACE[0] <= pace <= PACE[1]:
        track_flags.append(f"pace {pace} words per minute")
    expected = sum(len(tokens(item["text"])) for item in aligned)
    heard = sum(round(item["match"] * len(tokens(item["text"]))) for item in aligned)
    return {
        "match": round(heard / expected, 3) if expected else 1.0,
        "words_per_minute": pace,
        "flags": [*(flag for flags in sentence_flags.values() for flag in flags), *track_flags],
        "sentence_flags": sentence_flags,
        "track_flags": track_flags,
    }


def _recognize(build: Path, track: Path, language: str) -> tuple[list[TimedWord], float]:
    from tum_mcp.course.media.video_runtime import call_worker
    from tum_mcp.lecture_processing import runtime, transcription

    if not runtime.status().installed:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Listening uses the local speech recognizer: tum-mcp lecture runtime install.",
        )
    folder = build / "listen"
    windows = call_worker(
        {
            "action": "pcm16k",
            "file": str(track),
            "output": str(folder),
            "window": WINDOW,
            "step": STEP,
        },
        timeout=900,
    )
    words: list[TimedWord] = []
    model = "small.en" if language == "en" else "base"
    for index, window in enumerate(windows["windows"]):
        heard = transcription.recognize(Path(window["file"]), 0, model=model, language=language)
        until = (
            windows["windows"][index + 1]["offset"] + (WINDOW - STEP) / 2
            if index + 1 < len(windows["windows"])
            else float("inf")
        )
        since = window["offset"] + (WINDOW - STEP) / 2 if index else 0.0
        for segment in heard.segments:
            for word in segment.words:
                start = word.start + window["offset"]
                if since <= start < until:
                    words.append(
                        {"word": word.word, "start": start, "end": word.end + window["offset"]}
                    )
    for path in folder.glob("window-*.wav"):
        path.unlink()
    return words, windows["duration"]


def _recheck(build: Path, track: Path, language: str, aligned: list[AlignedSentence]) -> None:
    """Re-listen to each doubtful sentence alone: whole-track recognition drops or merges words
    at segment edges, so only a sentence that is still wrong in isolation stays flagged."""
    from tum_mcp.course.media.video_runtime import call_worker
    from tum_mcp.lecture_processing import transcription

    model = "small.en" if language == "en" else "base"
    doubtful = [s for s in aligned if _doubtful(s)]
    for sentence in doubtful[:24]:
        start = max(0.0, sentence["start"] - 0.3)
        cut = call_worker(
            {
                "action": "pcm16k",
                "file": str(track),
                "output": str(build / "listen"),
                "window": WINDOW,
                "step": STEP,
                "start": start,
                "end": sentence["end"] + 0.5,
            },
            timeout=300,
        )
        heard = transcription.recognize(
            Path(cut["windows"][0]["file"]), 0, model=model, language=language
        )
        words: list[TimedWord] = [
            {"word": w.word, "start": w.start + start, "end": w.end + start}
            for segment in heard.segments
            for w in segment.words
        ]
        again = align(
            [
                {
                    "key": sentence["key"],
                    "text": sentence["text"],
                    "start": sentence["start"],
                    "end": sentence["end"],
                }
            ],
            words,
        )[0]
        if again["match"] > sentence["match"]:
            sentence.update(again)
        sentence["rechecked"] = True


def _doubtful(sentence: AlignedSentence) -> bool:
    return (
        sentence["match"] < MATCH_FLOOR
        or bool(sentence["critical_edits"])
        or sentence["gap"] >= GAP
    )


def _write(
    root: Path,
    item: str,
    artifact_sha256: str,
    publication_sha256: str,
    expected: list[ExpectedSentence],
    words: list[TimedWord],
    duration: float,
    recheck: Callable[[list[AlignedSentence]], None],
) -> tuple[dict, list[dict], list[AlignedSentence]]:
    aligned = align(expected, words)
    recheck(aligned)
    verdict = judge(aligned, words)
    if not aligned:
        raise CampusError(
            Code.ACTION_REQUIRED, "There are no published narration sentences to check."
        )
    report = {
        "item": item,
        "artifact_sha256": artifact_sha256,
        "method_version": METHOD_VERSION,
        "method": "speech recognition (Whisper) aligned with the published script and timing",
        "covers": "what was said, completeness, numbers and negations, timing, pauses and pace; "
        "not voice naturalness or prosody",
        "duration": duration,
        **verdict,
        "sentences": aligned,
    }
    relative = _report_path(item)
    path = confined(root, relative)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
    private_write(path, data)
    evidence = {
        "kind": "listening",
        "path": relative,
        "sha256": hashlib.sha256(data).hexdigest(),
        "artifact_sha256": artifact_sha256,
        "intervals": [{"start": 0, "end": duration}],
    }
    receipt = ListeningReceipt(
        evidence=MediaEvidence.model_validate(evidence), publication_sha256=publication_sha256
    )
    private_write(_receipt_path(root, relative), receipt.model_dump_json(indent=2).encode())
    summary = {
        "item": item,
        "match": verdict["match"],
        "words_per_minute": verdict["words_per_minute"],
        "flags": verdict["flags"],
        "flagged_sentences": [
            {
                "key": s["key"],
                "text": s["text"],
                "heard": s["heard"],
                "match": s["match"],
                "missing": s["missing"],
                "critical_edits": s["critical_edits"],
            }
            for s in aligned
            if s["key"] in verdict["sentence_flags"]
        ],
        "report": relative,
    }
    return summary, [evidence], aligned


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def listen_audio(root: Path, stem: str, dispositions: tuple[str, ...] = ()) -> dict:
    from tum_mcp.course.media.audio import AudioManifest
    from tum_mcp.course.media.video_project import _read

    manifest = _read(confined(root, "audio/manifest.json"), AudioManifest)
    receipt = next(
        (r for r in (manifest.categories.values() if manifest else ()) if r.stem == stem), None
    )
    if receipt is None:
        raise CampusError(Code.ACTION_REQUIRED, f"Publish audio track {stem} first.")
    item = f"audio/{receipt.key}"
    publication = sha256(canonical(receipt.model_dump(mode="json")))
    relative = f"audio/{receipt.track.path}"
    artifact = file_hash(root, relative, receipt.track.sha256, receipt.track.size)
    if dispositions:
        return _dispose(root, item, artifact, publication, receipt.duration, 0.05, dispositions)
    build = confined(root, f"audio/.build/{stem}")
    timeline = build / "timeline.json"
    if not timeline.is_file():
        raise CampusError(Code.ACTION_REQUIRED, f"Publish {stem} again to record its timeline.")
    plan = json.loads(timeline.read_text(encoding="utf-8"))
    expected: list[ExpectedSentence] = [
        {
            "key": f"{s['chapter']}/{s['sentence']}",
            "text": s["text"],
            "start": s["start"],
            "end": s["end"],
        }
        for s in plan["sentences"]
    ]
    track = confined(root, relative)
    words, duration = _recognize(build, track, receipt.voice.language[:2])
    language = receipt.voice.language[:2]
    summary, evidence, _ = _write(
        root,
        item,
        file_hash(root, relative, artifact),
        publication,
        expected,
        words,
        duration,
        lambda aligned: _recheck(build, track, language, aligned),
    )
    return {**summary, "evidence": evidence}


def listen_video(root: Path, stem: str, dispositions: tuple[str, ...] = ()) -> dict:
    from tum_mcp.course.media.video_project import load_manifest
    from tum_mcp.course.media.video_runtime import call_worker

    manifest = load_manifest(root)
    receipt = manifest.videos.get(stem) if manifest else None
    if receipt is None:
        raise CampusError(Code.ACTION_REQUIRED, f"Publish video {stem} first.")
    item = f"video/{stem}"
    publication = sha256(canonical(receipt.model_dump(mode="json")))
    media = receipt.files["track"]
    relative = f"videos/{media.path}"
    artifact = file_hash(root, relative, media.sha256, media.size)
    if dispositions:
        return _dispose(root, item, artifact, publication, receipt.duration, 1 / 30, dispositions)
    expected: list[ExpectedSentence] = [
        {"key": f"{beat.key}/{index}", "text": cue.text, "start": cue.start, "end": cue.end}
        for beat in receipt.beats
        for index, cue in enumerate(beat.cues, 1)
    ]
    track = confined(root, relative)
    build = confined(root, f"videos/.build/{stem}")
    (build / "listen").mkdir(mode=0o700, parents=True, exist_ok=True)
    words, duration = _recognize(build, track, receipt.language[:2])
    summary, evidence, aligned = _write(
        root,
        item,
        file_hash(root, relative, artifact),
        publication,
        expected,
        words,
        duration,
        lambda aligned: _recheck(build, track, receipt.language[:2], aligned),
    )
    spoken = [s for s in aligned if s["start"] < duration]
    spoken = spoken[:: -(-len(spoken) // 48) or 1]
    moments = [round(s["start"] + (s["offset"] or 0) + 0.6, 2) for s in spoken]
    sheet = build / "listen" / "speech-frames.png"
    result = call_worker(
        {
            "action": "frames",
            "file": str(track),
            "times": moments,
            "labels": [s["key"] for s in spoken],
            "output": str(sheet),
        },
        timeout=600,
    )
    if not result.get("ok"):
        raise CampusError(Code.INVALID_RESPONSE, f"Frame extraction failed: {result.get('error')}")
    relative = sheet.resolve().relative_to(root.resolve()).as_posix()
    evidence.append(
        {
            "kind": "playback",
            "path": relative,
            "sha256": _file_sha(sheet),
            "artifact_sha256": artifact,
            "intervals": [{"start": 0, "end": duration}],
        }
    )
    return {
        **summary,
        "speech_aligned_frames": relative,
        "frame_times": [
            {"key": s["key"], "at": m, "text": s["text"]}
            for s, m in zip(spoken, moments, strict=True)
        ],
        "evidence": evidence,
    }
