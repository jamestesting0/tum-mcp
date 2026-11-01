"""Validate selected raster assets and transactionally manage only owned thumbnails."""

import re
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from tum_mcp.course_app_paths import app_folder, app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_content import LectureContent
from tum_mcp.lecture_evidence import Thumbnail
from tum_mcp.lecture_processing.visuals import raster
from tum_mcp.settings import Frozen
from tum_mcp.study_models import Digest
from tum_mcp.study_store import Write, digest, private_path, read_bytes

ASSET = re.compile(r"lecture-assets/[a-f0-9]{64}\.(png|jpg|webp)\Z")


class AssetRecord(Frozen):
    schema_version: Literal[1] = 1
    files: dict[str, Digest] = Field(default_factory=dict, max_length=10000)


def asset_writes(root: Path, content: LectureContent | None) -> tuple[Write, ...]:
    folder = app_folder(root)
    record_path = app_path(root, ".lecture-assets.json")
    previous = read_bytes(record_path)
    try:
        if previous is not None and len(previous) > 1024**2:
            raise ValueError("oversized")
        record = AssetRecord.model_validate_json(previous) if previous else AssetRecord()
        if any(ASSET.fullmatch(name) is None for name in record.files):
            raise ValueError("unconfined")
    except (ValidationError, ValueError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Edited lecture asset ownership needs review."
        ) from None
    thumbnails = (
        tuple(image for lecture in content.lectures for image in lecture.images) if content else ()
    )
    selected = {thumbnail.asset: thumbnail for thumbnail in thumbnails}
    if any(
        (thumbnail.width, thumbnail.height)
        != (selected[thumbnail.asset].width, selected[thumbnail.asset].height)
        for thumbnail in thumbnails
    ):
        raise CampusError(
            Code.INVALID_RESPONSE, "One lecture thumbnail has conflicting declared dimensions."
        )
    writes: list[Write] = []
    owned: dict[str, str] = {}
    for name, thumbnail in selected.items():
        public = app_path(root, name)
        private = private_path(root, name)
        source = private if private.exists() else public
        payload = thumbnail_bytes(source, thumbnail)
        before = read_bytes(public)
        if before is not None and digest(before) != thumbnail.sha256:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Edited public lecture thumbnail was preserved."
            )
        if before is None or name in record.files:
            writes.append(Write(f"{folder}/{name}", before, payload))
            owned[name] = thumbnail.sha256
    for name, expected in record.files.items():
        if name in selected:
            continue
        before = read_bytes(app_path(root, name))
        if before is not None and digest(before) != expected:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Edited obsolete lecture thumbnail was preserved."
            )
        writes.append(Write(f"{folder}/{name}", before, None))
    if previous is not None or owned:
        writes.append(
            Write(
                f"{folder}/.lecture-assets.json",
                previous,
                AssetRecord(files=owned).model_dump_json(indent=2).encode(),
            )
        )
    return tuple(writes)


def thumbnail_bytes(source: Path, thumbnail: Thumbnail) -> bytes:
    if not source.is_file() or source.stat().st_size > 16 * 1024**2:
        raise CampusError(
            Code.INVALID_RESPONSE, "Selected lecture thumbnail is missing or exceeds 16 MiB."
        )
    payload = source.read_bytes()
    if digest(payload) != thumbnail.sha256:
        raise CampusError(
            Code.STALE_RESULT, "Selected lecture thumbnail changed; preserve and review it."
        )
    signatures = {
        ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": payload.startswith(b"\xff\xd8\xff"),
        ".webp": payload[:4] == b"RIFF" and payload[8:12] == b"WEBP",
    }
    if not signatures[source.suffix]:
        raise CampusError(
            Code.INVALID_RESPONSE, "Lecture thumbnail format differs from its file extension."
        )
    with raster(payload) as image:
        if image.size != (thumbnail.width, thumbnail.height):
            raise CampusError(
                Code.INVALID_RESPONSE,
                "Lecture thumbnail dimensions differ from its declared source.",
            )
    return payload
