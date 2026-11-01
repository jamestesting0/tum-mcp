"""Public learning content, canonical recording links and referenced image bytes."""

from pathlib import Path

from pydantic import JsonValue, ValidationError

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_assets import thumbnail_bytes
from tum_mcp.lecture_content import NoteImage
from tum_mcp.lecture_evidence import Recording, Thumbnail
from tum_mcp.lecture_processing.timeline import watch_link
from tum_mcp.study_build import _inline_math
from tum_mcp.study_figures import figure_bytes as study_figure_bytes
from tum_mcp.study_figures import figure_images


def project(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Strip document provenance without removing internal learning references."""
    recordings: dict[str, JsonValue] = {}
    for lecture in payload.get("lectures", {}).get("lectures", []):
        recording = Recording.model_validate(lecture["recording"])
        url = watch_link(recording, 0).removesuffix("?t=0")
        recordings[recording.key] = {"title": lecture["title"], "url": url}
        lecture["source_link"] = url
        for note in lecture["notes"]:
            note["url"] = watch_link(recording, note["at_s"])
            note["recording_source"] = recording.key
        for highlight in lecture["highlights"]:
            highlight["url"] = watch_link(recording, highlight["interval"]["start_s"])
        lecture["recording"] = {
            "recorded_on": recording.recorded_on.isoformat(),
            "duration_s": recording.duration_s,
        }
        lecture["coverage"] = {
            name: lecture["coverage"][name] for name in ("status", "missing", "uncertain")
        }
    for name in (
        "sources",
        "inlineMath",
        "generation",
        "incompleteSources",
        "studyPreparation",
        "pending",
    ):
        payload.pop(name, None)
    recording_keys = set(recordings)
    public = {name: _public(value, recording_keys) for name, value in payload.items()}
    public["sources"] = recordings
    public["inlineMath"] = _inline_math(public)
    return public


def _public(value: JsonValue, recordings: set[str]) -> JsonValue:
    """Source fields have one meaning across the validated rich-content models."""
    match value:
        case list():
            return [_public(item, recordings) for item in value]
        case dict():
            result = {}
            for name, item in value.items():
                if name in {
                    "evidence",
                    "sha256",
                    "source_sha256",
                    "official_source",
                    "pages",
                    "crop",
                }:
                    continue
                if name == "sources":
                    references = []
                    for source in item:
                        match source:
                            case str() as key:
                                if key in recordings:
                                    references.append(key)
                            case {"key": str() as key}:
                                if key in recordings:
                                    references.append({"key": key})
                    result[name] = references
                else:
                    result[name] = _public(item, recordings)
            return result
        case _:
            return value


def assets(root: Path, payload: dict[str, JsonValue]) -> dict[str, bytes]:
    """Validate image provenance before the public projection removes it."""
    result = {
        image: study_figure_bytes(app_path(root, image)) for image in set(figure_images(payload))
    }
    try:
        for lecture in payload.get("lectures", {}).get("lectures", []):
            for note in lecture["notes"]:
                if note["image"] is not None:
                    image = NoteImage.model_validate(note["image"])
                    result[image.asset] = thumbnail_bytes(app_path(root, image.asset), image)
            for highlight in lecture["highlights"]:
                thumbnail = Thumbnail.model_validate(highlight["thumbnail"])
                result[thumbnail.asset] = thumbnail_bytes(
                    app_path(root, thumbnail.asset), thumbnail
                )
    except (KeyError, TypeError, ValidationError):
        raise CampusError(
            Code.INVALID_RESPONSE, "Rebuild selected lecture thumbnails before publishing."
        ) from None
    return result
