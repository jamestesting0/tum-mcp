"""Published audio for the local course app: the track index and the playlist download."""

import io
import json
import re
import zipfile
from pathlib import Path

from tum_mcp.course.media.audio import AudioChapters, AudioManifest, AudioReceipt
from tum_mcp.course.media.video_project import _read
from tum_mcp.course.project.store import confined
from tum_mcp.errors import CampusError, Code

BLOCK = re.compile(r"blocks\[(\d+)\]")


def _published(root: Path) -> list[tuple[AudioReceipt, Path]]:
    try:
        manifest = _read(confined(root, "audio/manifest.json"), AudioManifest, limit=4 * 1024**2)
    except (CampusError, OSError):
        return []
    tracks = []
    for receipt in sorted(manifest.categories.values() if manifest else (), key=lambda r: r.stem):
        try:
            path = confined(root, f"audio/{receipt.track.path}")
            present = path.is_file() and not path.is_symlink()
            present = present and path.stat().st_size == receipt.track.size
        except (CampusError, OSError):
            present = False
        if present:
            tracks.append((receipt, path))
    return tracks


def _chapters(root: Path, receipt: AudioReceipt) -> list[dict]:
    try:
        bounds = _read(confined(root, f"audio/{receipt.chapters.path}"), AudioChapters)
    except (CampusError, OSError):
        bounds = None
    chapters = []
    for bound in bounds.root if bounds else ():
        recall: list[dict] = []
        for item in receipt.coverage:
            if item.chapter != bound.key or item.mode == "missing":
                continue
            if item.kind in {"concept", "pattern"}:
                target = {"kind": item.kind, "key": item.unit}
            elif item.locator.kind == "block" and (match := BLOCK.fullmatch(item.locator.ref)):
                target = {"kind": "block", "unit": item.unit, "index": int(match[1])}
            else:
                continue
            if target not in recall:
                recall.append(target)
        chapters.append(
            {
                "key": bound.key,
                "title": bound.title,
                "start": bound.start,
                "end": bound.end,
                "recall": recall,
            }
        )
    return chapters


def _sentences(root: Path, receipt: AudioReceipt) -> list[dict]:
    # Publish records each sentence's place in the track; a timeline from another
    # assembly of the track is ignored rather than highlighting the wrong words.
    try:
        timeline = json.loads(
            confined(root, f"audio/.build/{receipt.stem}/timeline.json").read_text(encoding="utf-8")
        )
        if abs(float(timeline["total"]) - receipt.duration) > 1:
            return []
        return [
            {key: sentence[key] for key in ("chapter", "text", "start", "end")}
            for sentence in timeline["sentences"]
        ]
    except (CampusError, OSError, ValueError, KeyError, TypeError):
        return []


def preview_index(root: Path) -> dict:
    """Published tracks whose files are present, in playlist order. Never raises."""
    return {
        "tracks": [
            {
                "key": receipt.key,
                "stem": receipt.stem,
                "title": receipt.title,
                "kind": "study" if all(unit.kind == "unit" for unit in receipt.units) else "exam",
                "duration": receipt.duration,
                "track": f"audio/{receipt.track.path}",
                "script": f"audio/{receipt.script.path}",
                "revision": receipt.track.sha256[:16],
                "chapters": _chapters(root, receipt),
                "sentences": _sentences(root, receipt),
            }
            for receipt, _ in _published(root)
        ]
    }


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def playlist_zip(root: Path) -> tuple[str, bytes]:
    from tum_mcp.course.project.store import load_state

    tracks = _published(root)
    if not tracks:
        raise CampusError(Code.ACTION_REQUIRED, "No published audio tracks.")
    course = load_state(root).course
    title = getattr(course, "title", None) or course.key
    name = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "course"
    playlist = ["#EXTM3U"]
    readme = [f"{title}: audio notes", ""]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for receipt, path in tracks:
            archive.write(path, path.name)
            playlist += [f"#EXTINF:{round(receipt.duration)},{receipt.title}", path.name]
            readme.append(f"{path.name}  {receipt.title} ({_clock(receipt.duration)})")
        voice = tracks[0][0].voice
        readme += [
            "",
            "Each track has chapters; open playlist.m3u to play them in order.",
            f"Narration: {voice.provider} voice {voice.voice}, synthesized locally.",
        ]
        archive.writestr("playlist.m3u", "\n".join(playlist) + "\n")
        archive.writestr("README.txt", "\n".join(readme) + "\n")
    return f"{name}-audio-notes.zip", buffer.getvalue()
