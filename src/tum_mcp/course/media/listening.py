"""Machine listening for published narration: speech recognition aligned with the script and
its planned timing. It checks what was said and when, not how natural the voice sounds."""

import hashlib
import json
import re
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path

from tum_mcp.course.project.store import confined
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write

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


def tokens(text: str) -> list[str]:
    """Lowercase spoken words; digits become the words a narrator says for them."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"(\d)\s+\.\s*(\d)", r"\1.\2", text).lower().replace("’", "'")
    result: list[str] = []
    for raw in re.findall(r"[−-]?\d*\.?\d+|[a-z]+(?:'[a-z]+)?", text):
        if raw[0] in "−-." or raw[0].isdigit():
            negative = raw[0] in "−-"
            whole, _, fraction = raw.lstrip("−-").partition(".")
            words = (["minus"] if negative else []) + (_integer(int(whole)) if whole else [])
            if fraction:
                words += ["point", *(ONES[int(digit)] for digit in fraction)]
            result.extend(words)
        else:
            result.append(raw.replace("'", ""))
    return result


def align(expected: list[dict], words: list[dict]) -> list[dict]:
    result = []
    for sentence in expected:
        heard = [
            word
            for word in words
            if sentence["start"] - 0.35
            <= (word["start"] + word["end"]) / 2
            <= sentence["end"] + 0.35
        ]
        want = tokens(sentence["text"])
        got = tokens(" ".join(word["word"] for word in heard))
        matcher = SequenceMatcher(None, want, got, autojunk=False)
        kept = [False] * len(want)
        for block in matcher.get_matching_blocks():
            for index in range(block.a, block.a + block.size):
                kept[index] = True
        missing = [token for token, ok in zip(want, kept, strict=True) if not ok]
        run = gap = 0
        for ok in kept:
            run = 0 if ok else run + 1
            gap = max(gap, run)
        result.append(
            {
                **{key: sentence[key] for key in ("key", "text", "start", "end")},
                "heard": " ".join(word["word"].strip() for word in heard),
                "match": round(sum(kept) / len(want), 3) if want else 1.0,
                "missing": missing,
                "gap": gap,
                "offset": round(heard[0]["start"] - sentence["start"], 2) if heard else None,
                "spoken_words": len(got),
                "spoken_seconds": round(heard[-1]["end"] - heard[0]["start"], 2) if heard else 0.0,
            }
        )
    return result


def judge(aligned: list[dict], words: list[dict]) -> dict:
    flags = []
    for item in aligned:
        if item["match"] < MATCH_FLOOR:
            flags.append(f"unclear {item['key']}: heard '{item['heard'][:120]}'")
        elif item["gap"] >= GAP:
            flags.append(f"dropped {item['key']}: {item['gap']} words in a row not heard")
        critical = _critical(item["missing"])
        if critical:
            flags.append(f"missing {item['key']}: {', '.join(dict.fromkeys(critical))}")
        if item["offset"] is not None and abs(item["offset"]) > OFFSET_LIMIT:
            flags.append(f"timing {item['key']}: speech starts {item['offset']:+.2f} s from plan")
    planned = [(a["end"], b["start"]) for a, b in zip(aligned, aligned[1:], strict=False)]
    for before, after in zip(words, words[1:], strict=False):
        gap = after["start"] - before["end"]
        if gap > 2.0 and not any(
            a - 0.5 <= before["end"] and after["start"] <= b + 0.5 for a, b in planned
        ):
            flags.append(f"silence {before['end']:.1f}-{after['start']:.1f} s")
    spoken = sum(item["spoken_seconds"] for item in aligned)
    pace = round(60 * sum(item["spoken_words"] for item in aligned) / spoken) if spoken else 0
    if spoken and not PACE[0] <= pace <= PACE[1]:
        flags.append(f"pace {pace} words per minute")
    expected = sum(len(tokens(item["text"])) for item in aligned)
    heard = sum(round(item["match"] * len(tokens(item["text"]))) for item in aligned)
    return {
        "match": round(heard / expected, 3) if expected else 1.0,
        "words_per_minute": pace,
        "flags": flags,
    }


def _recognize(build: Path, track: Path, language: str) -> tuple[list[dict], float]:
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
    words: list[dict] = []
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


def _recheck(build: Path, track: Path, language: str, aligned: list[dict]) -> None:
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
        words = [
            {"word": w.word, "start": w.start + start, "end": w.end + start}
            for segment in heard.segments
            for w in segment.words
        ]
        again = align([sentence], words)[0]
        if again["match"] > sentence["match"]:
            sentence.update(
                {key: again[key] for key in ("heard", "match", "missing", "gap", "offset")}
            )
        sentence["rechecked"] = True


def _doubtful(sentence: dict) -> bool:
    return (
        sentence["match"] < MATCH_FLOOR
        or bool(_critical(sentence["missing"]))
        or sentence["gap"] >= GAP
    )


def _critical(missing: list[str]) -> list[str]:
    return [t for t in missing if t in NEGATIONS or t in ONES or t == "point"]


def _write(
    root: Path,
    item: str,
    artifact_sha256: str,
    expected: list[dict],
    words: list[dict],
    duration: float,
    recheck: Callable[[list[dict]], None],
) -> tuple[dict, list[dict], list[dict]]:
    aligned = align(expected, words)
    recheck(aligned)
    verdict = judge(aligned, words)
    name = item.replace("/", "-")
    report = {
        "item": item,
        "artifact_sha256": artifact_sha256,
        "method": "speech recognition (Whisper) aligned with the published script and timing",
        "covers": "what was said, completeness, numbers and negations, timing, pauses and pace; "
        "not voice naturalness or prosody",
        "duration": duration,
        **verdict,
        "sentences": aligned,
    }
    relative = f".tum-mcp/media-review/{name}-listening.json"
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
    flagged = [s for s in aligned if _doubtful(s)]
    summary = {
        "item": item,
        "match": verdict["match"],
        "words_per_minute": verdict["words_per_minute"],
        "flags": verdict["flags"],
        "flagged_sentences": [
            {key: s[key] for key in ("key", "text", "heard", "match", "missing")}
            for s in flagged[:40]
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


def listen_audio(root: Path, stem: str) -> dict:
    from tum_mcp.course.media.audio import AudioManifest
    from tum_mcp.course.media.video_project import _read

    manifest = _read(confined(root, "audio/manifest.json"), AudioManifest)
    receipt = next(
        (r for r in (manifest.categories.values() if manifest else ()) if r.stem == stem), None
    )
    if receipt is None:
        raise CampusError(Code.ACTION_REQUIRED, f"Publish audio track {stem} first.")
    build = confined(root, f"audio/.build/{stem}")
    timeline = build / "timeline.json"
    if not timeline.is_file():
        raise CampusError(Code.ACTION_REQUIRED, f"Publish {stem} again to record its timeline.")
    plan = json.loads(timeline.read_text(encoding="utf-8"))
    expected = [
        {
            "key": f"{s['chapter']}/{s['sentence']}",
            "text": s["text"],
            "start": s["start"],
            "end": s["end"],
        }
        for s in plan["sentences"]
    ]
    track = confined(root, f"audio/{receipt.track.path}")
    words, duration = _recognize(build, track, receipt.voice.language[:2])
    language = receipt.voice.language[:2]
    summary, evidence, _ = _write(
        root,
        f"audio/{receipt.key}",
        _file_sha(track),
        expected,
        words,
        duration,
        lambda aligned: _recheck(build, track, language, aligned),
    )
    return {**summary, "evidence": evidence}


def listen_video(root: Path, stem: str) -> dict:
    from tum_mcp.course.media.video_project import load_manifest
    from tum_mcp.course.media.video_runtime import call_worker

    manifest = load_manifest(root)
    receipt = manifest.videos.get(stem) if manifest else None
    if receipt is None:
        raise CampusError(Code.ACTION_REQUIRED, f"Publish video {stem} first.")
    expected = [
        {"key": f"{beat.key}/{index}", "text": cue.text, "start": cue.start, "end": cue.end}
        for beat in receipt.beats
        for index, cue in enumerate(beat.cues, 1)
    ]
    track = confined(root, f"videos/{receipt.files['track'].path}")
    build = confined(root, f"videos/.build/{stem}")
    words, duration = _recognize(build, track, receipt.language[:2])
    artifact = _file_sha(track)
    summary, evidence, aligned = _write(
        root,
        f"video/{stem}",
        artifact,
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
