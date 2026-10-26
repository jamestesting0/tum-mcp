import hashlib

import httpx2
import pytest
from pydantic import SecretStr

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import SilenceMarker
from tum_mcp.lecture_processing.hls import media_manifest, parse_playlist
from tum_mcp.lecture_processing.media import MediaCache, acquire
from tum_mcp.lecture_processing.media_budget import TransferBudget
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import ByteRange, MediaGrant, MediaRef
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate

URL = "https://media.example.invalid/recording/main.m3u8?jwt=synthetic-token"
GRANT = MediaGrant(playlist=SecretStr(URL))


def test_cookie_free_edge_client_drops_even_server_set_cookies_and_never_leaks_errors() -> None:
    seen = []

    def respond(request):
        seen.append(request)
        return httpx2.Response(200, content=b"segment", headers={"Set-Cookie": "edge=synthetic"})

    with MediaHTTP(GRANT, TransferBudget(), httpx2.MockTransport(respond)) as client:
        for _ in range(2):
            assert client.get(MediaRef(url=GRANT.resolve("one.ts"))).body == b"segment"
    assert all(
        "cookie" not in request.headers and "authorization" not in request.headers
        for request in seen
    )


def test_cache_revalidates_with_etag_and_reuses_unchanged_bytes(tmp_path) -> None:
    requests = []

    def respond(request):
        requests.append(request)
        if request.headers.get("if-none-match") == '"version-1"':
            return httpx2.Response(304)
        return httpx2.Response(
            200, content=b"verified-synthetic-bytes", headers={"ETag": '"version-1"'}
        )

    budget = TransferBudget()
    with MediaHTTP(GRANT, budget, httpx2.MockTransport(respond)) as client:
        cache = MediaCache(tmp_path / "cache", client)
        ref = MediaRef(url=GRANT.resolve("one.ts"))
        first, second = cache.get(ref), cache.get(ref)
        assert first.entry.sha256 == hashlib.sha256(b"verified-synthetic-bytes").hexdigest()
        assert second.reused and second.server_validated
        assert budget.used == len(b"verified-synthetic-bytes")
        assert requests[-1].headers["if-none-match"] == '"version-1"'


def test_acquisition_skips_silence_and_fetches_each_needed_segment_once(tmp_path) -> None:
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx2.Response(200, content=b"synthetic segment")

    manifest = media_manifest(
        parse_playlist(
            b"#EXTM3U\n#EXTINF:2,\na.ts\n#EXTINF:2,\nb.ts\n#EXTINF:2,\nc.ts\n#EXT-X-ENDLIST\n"
        ),
        GRANT,
        SecretStr(URL),
    )
    validity = evaluate(RecordingTiming(duration_s=6, silences=(SilenceMarker(start=2, end=4),)))
    with MediaHTTP(GRANT, TransferBudget(), httpx2.MockTransport(respond)) as client:
        result = acquire(manifest, MediaCache(tmp_path, client), validity)
    assert [item.segment.sequence for item in result] == [0, 2]
    assert sorted(calls) == ["/recording/a.ts", "/recording/c.ts"]


def test_whole_silence_prevents_even_a_seeded_cache_read(tmp_path) -> None:
    budget = TransferBudget()
    with MediaHTTP(
        GRANT, budget, httpx2.MockTransport(lambda r: pytest.fail("No media request"))
    ) as client:
        cache = MediaCache(tmp_path, client)
        validity = evaluate(
            RecordingTiming(duration_s=2, silences=(SilenceMarker(start=0, end=2),))
        )
        manifest = media_manifest(
            parse_playlist(b"#EXTM3U\n#EXTINF:2,\na.ts\n#EXT-X-ENDLIST\n"), GRANT, SecretStr(URL)
        )
        with pytest.raises(CampusError, match="whole_recording_silence"):
            acquire(manifest, cache, validity)
    assert list(tmp_path.glob("*.bin")) == []


@pytest.mark.parametrize("honor_range", [True, False])
def test_exact_and_ignored_byte_ranges_are_bounded(honor_range: bool) -> None:
    def respond(request):
        assert request.headers["range"] == "bytes=3-6"
        return (
            httpx2.Response(206, content=b"3456", headers={"Content-Range": "bytes 3-6/10"})
            if honor_range
            else httpx2.Response(200, content=b"0123456789")
        )

    with MediaHTTP(GRANT, TransferBudget(), httpx2.MockTransport(respond)) as client:
        ref = MediaRef(url=GRANT.resolve("one.ts"), byte_range=ByteRange(offset=3, length=4))
        assert client.get(ref).body == b"3456"


@pytest.mark.parametrize("status", [302, 401, 403])
def test_redirects_and_expired_capabilities_fail_without_signed_url_output(status: int) -> None:
    with MediaHTTP(
        GRANT,
        TransferBudget(),
        httpx2.MockTransport(
            lambda r: httpx2.Response(
                status, headers={"Location": "https://other.invalid/?jwt=synthetic-token"}
            )
        ),
    ) as client:
        with pytest.raises(CampusError) as error:
            client.get(MediaRef(url=GRANT.resolve("one.ts")))
    assert "synthetic-token" not in str(error.value)


def test_rate_limit_honors_capped_retry_after_with_exactly_three_attempts(monkeypatch) -> None:
    delays, calls = [], []
    budget = TransferBudget()
    monkeypatch.setattr(budget.cancelled, "wait", lambda delay: delays.append(delay) or False)

    def respond(request):
        calls.append(request)
        return httpx2.Response(429, headers={"Retry-After": "1000"})

    with MediaHTTP(GRANT, budget, httpx2.MockTransport(respond)) as client:
        with pytest.raises(CampusError) as error:
            client.get(MediaRef(url=GRANT.resolve("one.ts")))
    assert error.value.code == Code.RATE_LIMITED
    assert len(calls) == 3 and delays == [30, 30]


def test_budget_and_cancellation_preserve_existing_cache_files(tmp_path) -> None:
    keep = tmp_path / "user-note.txt"
    keep.write_text("Preserve this.")
    budget = TransferBudget(limit=3)
    with MediaHTTP(
        GRANT, budget, httpx2.MockTransport(lambda r: httpx2.Response(200, content=b"too-large"))
    ) as client:
        with pytest.raises(CampusError, match="budget"):
            MediaCache(tmp_path, client).get(MediaRef(url=GRANT.resolve("one.ts")))
        budget.cancelled.set()
        with pytest.raises(KeyboardInterrupt):
            client.get(MediaRef(url=GRANT.resolve("one.ts")))
    assert keep.read_text() == "Preserve this."
    assert list(tmp_path.glob("*.bin")) == []
