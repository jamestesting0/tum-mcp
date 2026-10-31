from typing import Final

import httpx2
import pytest

from tum_mcp.errors import CampusError
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.auth import resume_session
from tum_mcp.tumonline.identity import account_for_subject

COOKIE: Final = Cookie(name="session", value="synthetic-cookie", domain="campus.tum.de")


def test_refresh_verifies_server_identity_and_never_serializes_secrets() -> None:
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/auth/token/refresh"):
            return httpx2.Response(201, json={"accessToken": "synthetic-token"})
        if request.url.path.endswith("/desktop/profile"):
            return httpx2.Response(
                200,
                json={
                    "resource": [
                        {
                            "content": {
                                "desktopProfileLibDto": {
                                    "obfuscatedId": "synthetic-subject",
                                    "email": "ignored",
                                }
                            }
                        }
                    ]
                },
            )
        return httpx2.Response(200, json={"resource": []})

    session, _ = resume_session((COOKIE,), httpx2.MockTransport(handler))
    assert session.account == account_for_subject("synthetic-subject")
    assert len(seen) == 2
    assert "synthetic-token" not in repr(session)
    assert "synthetic-cookie" not in session.model_dump_json()
    assert "synthetic-subject" not in session.model_dump_json()


def test_wrong_identity_fails_closed() -> None:
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        if request.method == "POST":
            return httpx2.Response(201, json={"accessToken": "synthetic-token"})
        return httpx2.Response(
            200,
            json={
                "resource": [
                    {"content": {"desktopProfileLibDto": {"obfuscatedId": "different-subject"}}}
                ]
            },
        )

    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        resume_session(
            (COOKIE,), httpx2.MockTransport(handler), expected=account_for_subject("original")
        )
    assert len(seen) == 2


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (200, "INVALID_RESPONSE"),
        (204, "INVALID_RESPONSE"),
        (400, "INVALID_RESPONSE"),
        (302, "AUTH_REQUIRED"),
        (401, "AUTH_REQUIRED"),
        (403, "AUTH_REQUIRED"),
        (429, "RATE_LIMITED"),
        (500, "OFFLINE"),
    ],
)
def test_failed_refresh_never_echoes_response_or_sends_token(status: int, code: str) -> None:
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(
            status, headers={"Location": "https://example.invalid"}, text="private"
        )

    with pytest.raises(CampusError) as error:
        resume_session((COOKIE,), httpx2.MockTransport(handler))
    assert len(calls) == 1
    assert error.value.code == code
    assert "private" not in str(error.value)


def test_non_service_cookie_is_rejected_before_network() -> None:
    bad = Cookie(name="idp", value="synthetic-secret", domain="login.tum.de")
    transport = httpx2.MockTransport(lambda _: pytest.fail("network must not be contacted"))
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        resume_session((bad,), transport)


def test_anonymous_or_malformed_userinfo_is_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(201, json={"accessToken": "synthetic-token"})
        return httpx2.Response(
            200, json={"resource": [{"content": {"desktopProfileLibDto": {"nickname": "guest"}}}]}
        )

    with pytest.raises(CampusError):
        resume_session((COOKIE,), httpx2.MockTransport(handler))


def test_rotated_service_cookie_is_kept_but_foreign_cookie_is_not() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(
                201,
                headers=[
                    ("set-cookie", "session=rotated-synthetic; Path=/; Secure; HttpOnly"),
                    ("set-cookie", "foreign=synthetic; Domain=example.invalid; Path=/; Secure"),
                ],
                json={"accessToken": "synthetic-token"},
            )
        if request.url.path.endswith("/desktop/profile"):
            return httpx2.Response(
                200,
                json={
                    "resource": [
                        {"content": {"desktopProfileLibDto": {"obfuscatedId": "synthetic-subject"}}}
                    ]
                },
            )
        return httpx2.Response(200, json={"resource": []})

    session, _ = resume_session((COOKIE,), httpx2.MockTransport(handler))
    assert any(cookie.value == "rotated-synthetic" for cookie in session.cookies)
    assert all(cookie.domain.lstrip(".") == "campus.tum.de" for cookie in session.cookies)
    assert "rotated-synthetic" not in session.model_dump_json()


def test_policy_change_between_refresh_and_profile_prevents_next_request() -> None:
    calls = []
    checks = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.method)
        return httpx2.Response(201, json={"accessToken": "synthetic-token"})

    def authorize() -> None:
        checks.append(True)
        if len(checks) > 1:
            raise CampusError("SCOPE_DENIED", "synthetic scope denied")

    with pytest.raises(CampusError):
        resume_session((COOKIE,), httpx2.MockTransport(handler), authorize=authorize)
    assert calls == ["POST"]


def test_upstream_failure_is_not_reported_as_expired_login() -> None:
    with pytest.raises(CampusError) as error:
        resume_session((COOKIE,), httpx2.MockTransport(lambda _: httpx2.Response(503)))
    assert error.value.code.value == "OFFLINE"
