"""Installed Video and Audio Notes for a hosted site: static indexes and the files they name.

The local preview builds the same indexes on request, so the hosted site shows exactly the
media the local app shows. Drafts, build files, scripts for scenes and evidence stay local.
"""

import json
import re
from pathlib import Path
from typing import Final

from tum_mcp.course.project.store import confined

MEDIA: Final = re.compile(
    r"(videos/(tracks|captions|chapters|posters|narration)/[0-9a-z][0-9a-z_.-]{0,120}"
    r"\.(mp4|vtt|jpg|txt)|audio/tracks/[0-9a-z][0-9a-z_.-]{0,120}\.m4a"
    r"|audio/scripts/[0-9a-z][0-9a-z_.-]{0,120}\.txt"
    r"|videos/index\.json|audio/index\.json|audio/playlist\.zip)\Z"
)
# Published free-plan ElevenLabs content must name it in its title.
CREDIT: Final = " (elevenlabs.io)"
# A site without media still answers the app's index requests.
EMPTY: Final = {
    "videos/index.json": b'{"videos":{},"exercises":{},"patterns":{}}',
    "audio/index.json": b'{"tracks":[]}',
}


def _credited(entry: dict) -> dict:
    provider = entry.pop("provider", None)
    if isinstance(provider, str) and provider.casefold().startswith("elevenlabs"):
        entry["title"] += CREDIT
    return entry


def installed(root: Path) -> bool:
    from tum_mcp.course.media.audio_app import preview_index as audio_index
    from tum_mcp.course.media.video_project import preview_index as video_index

    return any(video_index(root).values()) or bool(audio_index(root)["tracks"])


def media_files(root: Path) -> dict[str, bytes]:
    """Indexes plus every file an index entry names; empty indexes when nothing is installed."""
    from tum_mcp.course.media.audio_app import playlist_zip
    from tum_mcp.course.media.audio_app import preview_index as audio_index
    from tum_mcp.course.media.video_project import preview_index as video_index

    output = dict(EMPTY)

    def add(path: str) -> None:
        if MEDIA.fullmatch(path) is None:
            raise ValueError(f"Unexpected media path {path}")
        output[path] = confined(root, path).read_bytes()

    videos = video_index(root)
    for group in videos.values():
        for entry in group.values():
            _credited(entry)
            for name in ("track", "captions", "poster", "transcript"):
                add(entry[name])
    if any(videos.values()):
        output["videos/index.json"] = json.dumps(videos, ensure_ascii=True).encode()
    audio = audio_index(root)
    for track in audio["tracks"]:
        _credited(track)
        add(track["track"])
        add(track["script"])
    if audio["tracks"]:
        name, output["audio/playlist.zip"] = playlist_zip(root)
        audio["download"] = name
        output["audio/index.json"] = json.dumps(audio, ensure_ascii=True).encode()
    return output
