"""Bounded VOD HLS parsing; never lets FFmpeg or the parser fetch network URLs."""

import re
from urllib.parse import urljoin

import m3u8
from pydantic import SecretStr, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.hls_wire import Playlist, Resource, Variant
from tum_mcp.lecture_processing.media_models import (
    MAX_PLAYLIST_BYTES,
    ByteRange,
    Manifest,
    MediaGrant,
    MediaRef,
    Segment,
)


def parse_playlist(payload: bytes) -> Playlist:
    if len(payload) > MAX_PLAYLIST_BYTES:
        raise CampusError(Code.INVALID_RESPONSE, "HLS metadata exceeds four MiB.")
    try:
        text = payload.decode("utf-8-sig")
        if not text.splitlines() or text.splitlines()[0].strip() != "#EXTM3U":
            raise CampusError(Code.INVALID_RESPONSE, "Expected an HLS playlist.")
        return Playlist.model_validate(m3u8.loads(text).data)
    except (ValueError, TypeError, KeyError):
        raise CampusError(
            Code.INVALID_RESPONSE, "HLS metadata is malformed or unsupported."
        ) from None


def variant_uri(playlist: Playlist, full_resolution: bool = False) -> SecretStr:
    """Choose the least expensive offered 720p-or-better variant; never guess URLs."""
    if not playlist.playlists:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "HLS master contains no playable variant.")

    def rank(item: Variant) -> tuple[bool, int]:
        resolution = re.fullmatch(r"(\d+)x(\d+)", item.stream_info.resolution or "")
        legible = (
            resolution is not None and int(resolution[1]) >= 1280 and int(resolution[2]) >= 720
        )
        return not legible, item.stream_info.bandwidth if legible else -item.stream_info.bandwidth

    chosen = (
        max(playlist.playlists, key=lambda item: item.stream_info.bandwidth)
        if full_resolution
        else min(playlist.playlists, key=rank)
    )
    if chosen.stream_info.audio:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Separate HLS audio renditions need a verified timing adapter.",
        )
    return chosen.uri


def media_manifest(playlist: Playlist, grant: MediaGrant, playlist_url: SecretStr) -> Manifest:
    if (
        playlist.is_variant
        or not playlist.is_endlist
        or playlist.is_i_frames_only
        or playlist.is_images_only
    ):
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Only complete finite audio/video VOD playlists are supported.",
        )
    if any(
        key is not None and key.method != "NONE" for key in playlist.keys + playlist.session_keys
    ):
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Encrypted/DRM HLS is unsupported.")
    ranges: dict[str, int] = {}

    def resource(value: Resource) -> MediaRef:
        url = grant.resolve(urljoin(playlist_url.get_secret_value(), value.uri.get_secret_value()))
        byte_range = None
        if value.byterange is not None:
            match = re.fullmatch(r"(\d+)(?:@(\d+))?", value.byterange)
            if match is None:
                raise CampusError(Code.INVALID_RESPONSE, "Invalid HLS byte range.")
            identity = MediaRef(url=url).key
            offset = int(match[2]) if match[2] else ranges.get(identity)
            if offset is None:
                raise CampusError(
                    Code.INVALID_RESPONSE, "Implicit HLS range lacks a preceding range."
                )
            try:
                byte_range = ByteRange(offset=offset, length=int(match[1]))
            except ValidationError:
                raise CampusError(
                    Code.INVALID_RESPONSE, "HLS byte range exceeds its bound."
                ) from None
            ranges[identity] = byte_range.offset + byte_range.length
        return MediaRef(url=url, byte_range=byte_range)

    segments: list[Segment] = []
    offset, discontinuity = 0.0, playlist.discontinuity_sequence or 0
    for index, part in enumerate(playlist.segments):
        if part.gap_tag:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "HLS contains unavailable media intervals."
            )
        discontinuity += int(part.discontinuity)
        end = offset + part.duration
        if end > 28800:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "Recording exceeds the eight-hour bound."
            )
        segments.append(
            Segment(
                sequence=(playlist.media_sequence or 0) + index,
                span=Interval(start_s=offset, end_s=end),
                media=resource(part),
                initialization=resource(part.init_section) if part.init_section else None,
                discontinuity=discontinuity,
            )
        )
        offset = end
    try:
        return Manifest(segments=tuple(segments))
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "HLS contains no bounded media segments."
        ) from None
