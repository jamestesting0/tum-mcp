"""Authorized recording playlist access, before content acquisition."""

from urllib.parse import urljoin, urlsplit

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.hls import media_manifest, parse_playlist, variant_uri
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import (
    MAX_PLAYLIST_BYTES,
    Manifest,
    MediaGrant,
    MediaRef,
)
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate, require_content
from tum_mcp.tum_live.wire import Watch


def media_grant(watch: Watch) -> MediaGrant:
    """Use only the provider's signed view field after course membership verification."""
    validity = evaluate(
        RecordingTiming(
            duration_s=watch.stream.duration,
            silences=watch.silences,
            start_offset_s=watch.start_offset,
            end_offset_s=watch.end_offset,
        )
    )
    if validity.status == "invalid":
        require_content(validity)
    if not watch.stream.recording or watch.stream.live_now:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Prepare a finished recording, not a live stream."
        )
    for kind in (
        "WATCH_VIEW_KIND_PRESENTATION",
        "WATCH_VIEW_KIND_COMBINED",
        "WATCH_VIEW_KIND_CAMERA",
    ):
        for view in watch.views:
            if view.kind == kind:
                grant = MediaGrant(playlist=view.playlist_url)
                grant.resolve(view.playlist_url.get_secret_value())
                return grant
    raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Recording has no authorized playable view.")


def load_manifest(client: MediaHTTP, *, full_resolution: bool = False) -> Manifest:
    """Fetch at most three bounded playlist levels; no media bytes before validity."""
    grant = client.grant
    url = grant.resolve(grant.playlist.get_secret_value())
    visited: set[str] = set()
    for _ in range(3):
        if not urlsplit(url.get_secret_value()).path.lower().endswith(".m3u8"):
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "Duration discovery permits HLS metadata only."
            )
        ref = MediaRef(url=url)
        if ref.key in visited:
            raise CampusError(Code.INVALID_RESPONSE, "HLS playlist reference cycle.")
        visited.add(ref.key)
        client.budget.check()
        payload = client.playlist_cache.get(ref.key)
        if payload is None:
            payload = client.get(ref, limit=MAX_PLAYLIST_BYTES).body
            if len(client.playlist_cache) >= 6:
                client.playlist_cache.pop(next(iter(client.playlist_cache)))
            client.playlist_cache[ref.key] = payload
        playlist = parse_playlist(payload)
        if not playlist.is_variant:
            return media_manifest(playlist, grant, url)
        url = grant.resolve(
            urljoin(
                url.get_secret_value(), variant_uri(playlist, full_resolution).get_secret_value()
            )
        )
    raise CampusError(Code.CAPABILITY_UNSUPPORTED, "HLS exceeds three playlist levels.")
