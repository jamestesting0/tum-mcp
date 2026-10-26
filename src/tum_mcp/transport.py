"""Bounded provider HTTP operations with endpoint and origin enforcement."""

import logging
import re
import socket
from collections.abc import Mapping
from typing import Final, Literal, assert_never

import httpx2

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import Session
from tum_mcp.moodle.http_client import cookie_jar
from tum_mcp.settings import Account, Provider

READ_PATHS: Final = {
    Provider.TUM_LIVE: re.compile(
        r"/api/v2/users/me|/api/v2/courses/enrolled|/api/v2/courses/[A-Za-z0-9_-]{1,100}|"
        r"/api/v2/streams/[A-Za-z0-9_-]{1,100}/\d+/watch|"
        r"/api/v2/streams/[A-Za-z0-9_-]{1,100}/\d+/subtitles/[A-Za-z0-9_-]{1,30}|"
        r"/api/v2/streams/\d+/files/\d+"
    ),
    Provider.ZULIP: re.compile(
        r"/api/v1/(server_settings|users/me|streams|users/me/subscriptions|"
        r"users/me/\d+/topics|messages(?:/\d+)?)"
    ),
    Provider.ARTEMIS: re.compile(
        r"/management/info|/api/core/public/account|/api/course/courses/for-dropdown|"
        r"/api/course/courses/\d+/(for-overview|exercises-for-overview)|"
        r"/api/lecture/courses/\d+/lectures-for-overview|"
        r"/api/lecture/lectures/\d+/details|"
        r"/api/core/files/attachments/attachment-video-units/\d+/student/[a-zA-Z0-9_.%-]+|"
        r"/api/exercise/exercises/\d+/details|"
        r"/api/programming/programming-exercise-participations/\d+/"
        r"student-participation-with-all-results|"
        r"/api/assessment/participations/\d+/results/\d+/details"
    ),
}
PUBLIC_PATHS: Final = {"/management/info", "/api/v1/server_settings"}
MAX_RESPONSE: Final = 4 * 1024 * 1024


class API:
    def __init__(
        self,
        account: Account,
        credential: Credential | None = None,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self.account = account
        self.credential = credential
        self.transport = transport

    def get(self, path: str, params: Mapping[str, str] | None = None) -> bytes:
        if not READ_PATHS[self.account.provider].fullmatch(path):
            raise CampusError(Code.SCOPE_DENIED, "This endpoint is not an enabled read operation.")
        return self._request("GET", path, params)

    def get_lecture_file(self, path: str) -> bytes:
        if self.account.provider != Provider.ARTEMIS or not re.fullmatch(
            r"/api/core/files/attachments/attachment-video-units/\d+/student/[a-zA-Z0-9_.%-]+",
            path,
        ):
            raise CampusError(Code.SCOPE_DENIED, "Only student lecture files can be retrieved.")
        return self._request("GET", path, None, response_limit=50 * 1024 * 1024)

    def get_tum_live_file(self, stream_id: int, file_id: int) -> bytes:
        """Keep the binary budget separate from the metadata-response limit."""
        if self.account.provider != Provider.TUM_LIVE or min(stream_id, file_id) <= 0:
            raise CampusError(
                Code.SCOPE_DENIED, "Only a discovered TUM-Live file can be retrieved."
            )
        return self._request(
            "GET",
            f"/api/v2/streams/{stream_id}/files/{file_id}",
            None,
            response_limit=64 * 1024 * 1024,
        )

    def _start_once(self, exercise_id: int, *, practice: bool) -> bytes:
        """Retired compatibility entry point; campus access is permanently read-only."""
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Campus access is read-only; exercise start is unavailable.",
        )

    def _request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        params: Mapping[str, str] | None,
        *,
        response_limit: int = MAX_RESPONSE,
    ) -> bytes:
        if method != "GET" or not READ_PATHS[self.account.provider].fullmatch(path):
            raise CampusError(Code.SCOPE_DENIED, "Campus access permits read requests only.")
        credential = None
        if path not in PUBLIC_PATHS:
            credential = self.credential or Vault().load(self.account)
            if credential.account_id != self.account.id:
                raise CampusError(Code.SCOPE_DENIED, "Credential account mismatch.")
        headers = {"Accept": "application/json"}
        cookies = httpx2.Cookies()
        basic = None
        if credential:
            match self.account.provider:
                case Provider.ZULIP:
                    if credential.authentication == "browser_session":
                        if not credential.cookies or method != "GET":
                            raise CampusError(
                                Code.AUTH_REQUIRED, "Reconnect the Zulip browser session."
                            )
                        cookies = cookie_jar(
                            Session(generation="", cookies=list(credential.cookies), verified_at=0)
                        )
                        path = "/json/" + path.removeprefix("/api/v1/")
                    else:
                        basic = httpx2.BasicAuth(
                            credential.username.get_secret_value(),
                            credential.api_key.get_secret_value(),
                        )
                case Provider.ARTEMIS | Provider.TUM_LIVE:
                    cookies = cookie_jar(
                        Session(generation="", cookies=list(credential.cookies), verified_at=0)
                    )
                case unreachable:
                    assert_never(unreachable)
        transport = self.transport or httpx2.HTTPTransport(
            http2=True,
            retries=2 if method == "GET" else 0,
            limits=httpx2.Limits(max_connections=4, max_keepalive_connections=2),
            socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
        )
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        logging.getLogger("httpcore2").setLevel(logging.WARNING)
        try:
            with (
                httpx2.Client(
                    transport=transport,
                    timeout=httpx2.Timeout(20, connect=5),
                    headers=headers,
                    cookies=cookies,
                    auth=basic,
                    follow_redirects=False,
                ) as client,
                client.stream(method, self.account.origin + path, params=params) as response,
            ):
                if response.status_code in {401, 403}:
                    raise CampusError(
                        Code.AUTH_REQUIRED,
                        "Account access denied; reconnect or check server permissions.",
                    )
                if response.status_code == 429:
                    raise CampusError(Code.RATE_LIMITED, "Provider rate limit; retry later.")
                if response.is_redirect:
                    raise CampusError(
                        Code.SCOPE_DENIED, "Provider redirect rejected; reconnect if needed."
                    )
                if not response.is_success:
                    raise CampusError(
                        Code.CAPABILITY_UNSUPPORTED,
                        f"Provider returned HTTP {response.status_code}.",
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > response_limit:
                        raise CampusError(
                            Code.INVALID_RESPONSE, "Response exceeded the retrieval budget."
                        )
                return bytes(body)
        except httpx2.HTTPError:
            raise CampusError(
                Code.OFFLINE, "Provider request failed; credentials and URLs omitted."
            ) from None
