from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.decoding import run_decoder
from tum_mcp.lecture_processing.media import MediaCache
from tum_mcp.lecture_processing.media_budget import TransferBudget
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import ByteRange, MediaGrant, MediaRef
from tum_mcp.lecture_processing.playlists import load_manifest

GRANT = MediaGrant(
    playlist=SecretStr("https://media.example.invalid/recording/main.m3u8?jwt=synthetic")
)


def test_private_dns_destination_is_rejected_before_opening_a_request(monkeypatch) -> None:
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    monkeypatch.setattr(httpx2.Client, "stream", lambda *a, **k: pytest.fail("No private request"))
    with MediaHTTP(GRANT, TransferBudget()) as client:
        with pytest.raises(CampusError) as error:
            client.get(MediaRef(url=GRANT.resolve("one.ts")))
    assert error.value.code == Code.SCOPE_DENIED


def test_duration_discovery_never_fetches_a_binary_variant_uri() -> None:
    visited = []

    def respond(request):
        visited.append(request.url.path)
        return httpx2.Response(
            200, content=b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nsegment.ts\n"
        )

    with MediaHTTP(GRANT, TransferBudget(), httpx2.MockTransport(respond)) as client:
        with pytest.raises(CampusError) as error:
            load_manifest(client)
    assert error.value.code == Code.CAPABILITY_UNSUPPORTED
    assert visited == ["/recording/main.m3u8"]


def test_cache_corruption_is_replaced_only_after_verified_fresh_retrieval(tmp_path: Path) -> None:
    with MediaHTTP(
        GRANT,
        TransferBudget(),
        httpx2.MockTransport(lambda request: httpx2.Response(200, content=b"correct")),
    ) as client:
        cache = MediaCache(tmp_path, client)
        ref = MediaRef(url=GRANT.resolve("one.ts"))
        before = cache.get(ref)
        before.path.write_bytes(b"corrupt")
        after = cache.get(ref)
    assert not after.reused and after.path.read_bytes() == b"correct"
    assert before.entry.sha256 == after.entry.sha256


def test_symbolic_cached_media_is_preserved_without_reading_an_external_file(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("Preserve outside.")
    with MediaHTTP(
        GRANT,
        TransferBudget(),
        httpx2.MockTransport(lambda request: httpx2.Response(200, content=b"correct")),
    ) as client:
        cache = MediaCache(tmp_path / "cache", client)
        ref = MediaRef(url=GRANT.resolve("one.ts"))
        before = cache.get(ref)
        before.path.unlink()
        try:
            before.path.symlink_to(outside)
        except OSError:
            pytest.skip("Host does not permit fixture symlinks.")
        with pytest.raises(CampusError) as error:
            cache.get(ref)
    assert error.value.code == Code.WORKSPACE_CONFLICT
    assert outside.read_text() == "Preserve outside."


def test_mismatched_range_response_never_enters_cache(tmp_path: Path) -> None:
    with MediaHTTP(
        GRANT,
        TransferBudget(),
        httpx2.MockTransport(
            lambda request: httpx2.Response(
                206, content=b"3456", headers={"Content-Range": "bytes 0-3/10"}
            )
        ),
    ) as client:
        with pytest.raises(CampusError) as error:
            MediaCache(tmp_path, client).get(
                MediaRef(
                    url=GRANT.resolve("one.ts"),
                    byte_range=ByteRange(offset=3, length=4),
                )
            )
    assert error.value.code == Code.INVALID_RESPONSE
    assert list(tmp_path.glob("*.bin")) == []


def test_oversized_response_is_rejected_before_body_iteration() -> None:
    class Unreadable(httpx2.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            pytest.fail("Oversized response body must not be read.")

    budget = TransferBudget()
    with MediaHTTP(
        GRANT,
        budget,
        httpx2.MockTransport(
            lambda request: httpx2.Response(
                200, headers={"Content-Length": "5000000"}, stream=Unreadable()
            )
        ),
    ) as client:
        with pytest.raises(CampusError) as error:
            client.get(MediaRef(url=GRANT.resolve("large.m3u8")), limit=4 * 1024 * 1024)
    assert error.value.code == Code.INVALID_RESPONSE and budget.used == 0


@pytest.mark.parametrize(
    "argv",
    [
        ("python", "-c", "print('not allowed')"),
        ("ffmpeg", "-i", "https://media.example.invalid/?jwt=synthetic"),
    ],
)
def test_decoder_cannot_be_used_as_a_remote_downloader_or_arbitrary_launcher(argv) -> None:
    with pytest.raises(CampusError) as error:
        run_decoder(argv)
    assert error.value.code == Code.SCOPE_DENIED
