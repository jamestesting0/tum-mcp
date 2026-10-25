from pathlib import Path

import httpx2
import pytest
from keyring.backend import KeyringBackend

from tum_mcp.moodle import http_client
from tum_mcp.moodle.auth import Cookie, Session, SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.moodle.errors import MoodleError


def make_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionStore:
    store = SessionStore(Paths(tmp_path))
    store.save(
        Session(
            generation=store.begin_login(),
            verified_at=0,
            cookies=[Cookie(name="MoodleSession", value="sensitive", domain="www.moodle.tum.de")],
        )
    )
    monkeypatch.setattr(http_client, "public_address", lambda: None)
    return store


def test_external_redirect_is_blocked_before_cookie_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory_keyring: KeyringBackend
) -> None:
    store = make_store(tmp_path, monkeypatch)
    requests: list[httpx2.Request] = []
    client_class = httpx2.Client

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(302, headers={"Location": "https://evil.example/steal"})

    monkeypatch.setattr(
        httpx2,
        "Client",
        lambda **kwargs: client_class(transport=httpx2.MockTransport(handler), **kwargs),
    )
    with pytest.raises(MoodleError, match="UNSAFE_URL"):
        http_client.MoodleHTTP(store).get("/course/view.php?id=1")
    assert len(requests) == 1
    assert requests[0].url.host == "www.moodle.tum.de"


def test_login_html_is_not_returned_as_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory_keyring: KeyringBackend
) -> None:
    store = make_store(tmp_path, monkeypatch)
    client_class = httpx2.Client
    monkeypatch.setattr(
        httpx2,
        "Client",
        lambda **kwargs: client_class(
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(
                    200, headers={"Content-Type": "text/html"}, content=b'<form id="login"></form>'
                )
            ),
            **kwargs,
        ),
    )
    with pytest.raises(MoodleError, match="SESSION_EXPIRED"):
        http_client.MoodleHTTP(store).get("/course/view.php?id=1")


def test_actual_response_bytes_enforce_download_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_keyring: KeyringBackend,
) -> None:
    store = make_store(tmp_path, monkeypatch)
    client_class = httpx2.Client
    monkeypatch.setattr(http_client, "MAX_BYTES", 10)
    monkeypatch.setattr(
        httpx2,
        "Client",
        lambda **kwargs: client_class(
            transport=httpx2.MockTransport(lambda request: httpx2.Response(200, content=b"x" * 11)),
            **kwargs,
        ),
    )
    with pytest.raises(MoodleError, match="TOO_LARGE"):
        http_client.MoodleHTTP(store).get("/pluginfile.php/1/document.pdf")
