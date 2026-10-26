"""Refresh a TUMonline session and verify its identity without exposing credentials."""

import logging
import socket
from collections.abc import Callable
from typing import Final

import httpx2
from pydantic import ConfigDict, Field, SecretStr, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import Cookie, Session
from tum_mcp.moodle.http_client import cookie_jar
from tum_mcp.settings import Frozen
from tum_mcp.tumonline.identity import AccountRef, account_for_subject

ORIGIN: Final = "https://campus.tum.de"
REFRESH: Final = "/tumonline/ee/rest/auth/token/refresh"
PROFILE: Final = "/tumonline/ee/rest/brm.lib.dtop.home/v1/desktop/profile"
STUDIES: Final = "/tumonline/ee/rest/slc.cm.cs/student/myStudies/chooser"
MAX_RESPONSE: Final = 256 * 1024


class Refresh(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore")
    accessToken: SecretStr = Field(repr=False, exclude=True)


class Profile(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore")
    obfuscatedId: str = Field(min_length=1, max_length=512, repr=False, exclude=True)


class ProfileContent(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore")
    desktopProfileLibDto: Profile


class ProfileResource(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore")
    content: ProfileContent


class ProfileResponse(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore")
    resource: tuple[ProfileResource, ...] = Field(min_length=1, max_length=1)


class ResumedSession(Frozen):
    account: AccountRef
    token: SecretStr = Field(repr=False, exclude=True)
    cookies: tuple[Cookie, ...] = Field(repr=False, exclude=True)
    studies: bytes = Field(default=b"", repr=False, exclude=True)


class IdentityMismatch(CampusError):
    """The refreshed session belongs to a different account."""

    def __init__(self) -> None:
        super().__init__(Code.SCOPE_DENIED, "TUMonline account identity changed.")


def read_response(client: httpx2.Client, request: httpx2.Request, expected: int) -> bytes:
    """Bound response bytes and return only generic failures."""
    with client.stream(
        request.method, request.url, headers=request.headers, content=request.content
    ) as response:
        if response.status_code == 429:
            raise CampusError(Code.RATE_LIMITED, "TUMonline rate limit; retry later.")
        if response.status_code >= 500:
            raise CampusError(Code.OFFLINE, "TUMonline is temporarily unavailable.")
        if response.status_code != expected:
            if response.status_code in {401, 403} or response.is_redirect:
                raise CampusError(Code.AUTH_REQUIRED, "Reconnect the TUMonline account.")
            raise CampusError(Code.INVALID_RESPONSE, "TUMonline returned an unexpected response.")
        body = bytearray()
        for chunk in response.iter_bytes():
            if len(body) + len(chunk) > MAX_RESPONSE:
                raise CampusError(Code.INVALID_RESPONSE, "TUMonline response exceeded its limit.")
            body.extend(chunk)
        return bytes(body)


def resume_session(
    cookies: tuple[Cookie, ...],
    transport: httpx2.BaseTransport | None = None,
    *,
    expected: AccountRef | None = None,
    authorize: Callable[[], None] | None = None,
    read_studies: bool = True,
    checkpoint_cookies: Callable[[tuple[Cookie, ...]], None] | None = None,
) -> ResumedSession:
    """Refresh service cookies and bind the account to the authenticated desktop identity."""
    if not cookies or any(c.domain.lstrip(".") != "campus.tum.de" or not c.secure for c in cookies):
        raise CampusError(Code.SCOPE_DENIED, "TUMonline service cookies are invalid.")
    session = Session(generation="", cookies=list(cookies), verified_at=0)
    backend = transport or httpx2.HTTPTransport(
        http2=True,
        retries=0,
        limits=httpx2.Limits(max_connections=2, max_keepalive_connections=1),
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    # HTTP transport and HTTP/2 compression debug logs include raw headers.
    for name in ("httpx2", "httpcore2.http11", "httpcore2.http2", "hpack.hpack", "hpack.table"):
        logger = logging.getLogger(name)
        logger.setLevel(max(logger.getEffectiveLevel(), logging.WARNING))
    try:
        with httpx2.Client(
            transport=backend,
            cookies=cookie_jar(session),
            timeout=httpx2.Timeout(20, connect=5),
            follow_redirects=False,
            headers={"Accept": "application/json"},
        ) as client:

            def service_cookies() -> tuple[Cookie, ...]:
                return tuple(
                    Cookie(
                        name=c.name,
                        value=c.value,
                        domain=c.domain,
                        path=c.path,
                        secure=c.secure,
                        expires=c.expires or -1,
                    )
                    for c in client.cookies.jar
                    if c.domain.lstrip(".") == "campus.tum.de" and c.secure
                )

            def read_and_checkpoint(request: httpx2.Request, status: int) -> bytes:
                try:
                    return read_response(client, request, status)
                finally:
                    retained = service_cookies()
                    if checkpoint_cookies is not None and retained:
                        checkpoint_cookies(retained)

            refresh_request = client.build_request(
                "POST", ORIGIN + REFRESH, content=b"", headers={"Content-Type": "application/json"}
            )
            if authorize is not None:
                authorize()
            refresh_body = read_and_checkpoint(refresh_request, 201)
            refresh = Refresh.model_validate_json(refresh_body)
            token = refresh.accessToken.get_secret_value()
            if not token:
                raise CampusError(Code.AUTH_REQUIRED, "Reconnect the TUMonline account.")

            identity_request = client.build_request(
                "GET", ORIGIN + PROFILE, headers={"Authorization": "Bearer " + token}
            )
            if authorize is not None:
                authorize()
            identity = ProfileResponse.model_validate_json(
                read_and_checkpoint(identity_request, 200)
            )
            account = account_for_subject(
                identity.resource[0].content.desktopProfileLibDto.obfuscatedId
            )
            if expected is not None and account != expected:
                raise IdentityMismatch()
            studies = b""
            if read_studies:
                studies_request = client.build_request(
                    "GET", ORIGIN + STUDIES, headers={"Authorization": "Bearer " + token}
                )
                if authorize is not None:
                    authorize()
                studies = read_and_checkpoint(studies_request, 200)
            retained = service_cookies()
            if not retained:
                raise CampusError(Code.AUTH_REQUIRED, "TUMonline session cookies are unavailable.")
            return ResumedSession(
                account=account, token=refresh.accessToken, cookies=retained, studies=studies
            )
    except httpx2.HTTPError:
        raise CampusError(Code.OFFLINE, "TUMonline session check failed.") from None
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "TUMonline identity format could not be verified."
        ) from None
