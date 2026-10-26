import pytest
from pydantic import SecretStr

from tum_mcp.errors import CampusError
from tum_mcp.lecture_processing.hls import media_manifest, parse_playlist, variant_uri
from tum_mcp.lecture_processing.media_models import MediaGrant, MediaRef

URL = "https://media.example.invalid/recording/main.m3u8?jwt=synthetic-token"
GRANT = MediaGrant(playlist=SecretStr(URL))


def test_finite_vod_preserves_sequence_ranges_discontinuity_and_initialization() -> None:
    wire = parse_playlist(b"""#EXTM3U
#EXT-X-MEDIA-SEQUENCE:9
#EXT-X-MAP:URI="init.mp4",BYTERANGE="100@0"
#EXTINF:8,
#EXT-X-BYTERANGE:500@100
movie.mp4
#EXT-X-DISCONTINUITY
#EXTINF:5,
#EXT-X-BYTERANGE:600
movie.mp4
#EXT-X-ENDLIST
""")
    manifest = media_manifest(wire, GRANT, SecretStr(URL))
    first, second = manifest.segments
    assert (first.sequence, second.sequence) == (9, 10)
    assert (second.span.start_s, second.span.end_s) == (8, 13)
    assert first.media.byte_range.offset == 100 and second.media.byte_range.offset == 600
    assert first.initialization.byte_range.length == 100
    assert second.discontinuity == 1


def test_variant_selection_preserves_readable_visuals_at_lowest_offered_bandwidth() -> None:
    wire = parse_playlist(b"""#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=100000,RESOLUTION=320x180
small.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1920x1080
high.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=400000,RESOLUTION=1280x720
medium.m3u8
""")
    assert variant_uri(wire).get_secret_value() == "medium.m3u8"
    assert variant_uri(wire, full_resolution=True).get_secret_value() == "high.m3u8"


@pytest.mark.parametrize(
    "uri",
    [
        "https://other.invalid/recording/part.ts",
        "../other/part.ts",
        "file:///private/source.ts",
        "https://student:password@media.example.invalid/recording/part.ts",
        "/recording/%252e%252e/private.ts",
    ],
)
def test_hls_uri_cannot_expand_the_recording_grant(uri: str) -> None:
    wire = parse_playlist(f"#EXTM3U\n#EXTINF:8,\n{uri}\n#EXT-X-ENDLIST\n".encode())
    with pytest.raises(CampusError):
        media_manifest(wire, GRANT, SecretStr(URL))


@pytest.mark.parametrize(
    "text",
    [
        "#EXTM3U\n#EXTINF:8,\nx.ts\n",
        '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n#EXTINF:8,\nx.ts\n#EXT-X-ENDLIST\n',
        "#EXTM3U\n#EXTINF:nan,\nx.ts\n#EXT-X-ENDLIST\n",
        "#EXTM3U\n#EXTINF:8,\n#EXT-X-BYTERANGE:100\nx.ts\n#EXT-X-ENDLIST\n",
    ],
)
def test_unverified_or_malformed_playlists_never_become_ready_media(text: str) -> None:
    with pytest.raises(CampusError):
        wire = parse_playlist(text.encode())
        media_manifest(wire, GRANT, SecretStr(URL))


def test_capability_rotation_preserves_cache_identity_but_quality_changes_do_not() -> None:
    first = MediaRef(url=SecretStr(URL + "&quality=720"))
    rotated = MediaRef(
        url=SecretStr(URL.replace("synthetic-token", "rotated-token") + "&quality=720")
    )
    high = MediaRef(url=SecretStr(URL + "&quality=1080"))
    assert first.key == rotated.key
    assert first.key != high.key
    assert "synthetic-token" not in first.model_dump_json() + repr(first)
