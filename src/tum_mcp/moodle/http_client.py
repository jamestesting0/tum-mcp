import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass
from http.cookiejar import Cookie as JarCookie
from typing import Literal
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import httpx2
from filelock import FileLock, Timeout
from pydantic import JsonValue, TypeAdapter

from tum_mcp.moodle.auth import Cookie, Session, SessionStore
from tum_mcp.moodle.config import BASE_URL, MAX_BYTES, private_write
from tum_mcp.moodle.errors import ErrorCode, MoodleError


def safe_url(url: str) -> str:
    parts = urlsplit(urljoin(f"{BASE_URL}/", url))
    try:
        port = parts.port
    except ValueError:
        raise MoodleError(ErrorCode.UNSAFE_URL, "Invalid server port.") from None
    if (
        parts.scheme != "https"
        or parts.hostname != "www.moodle.tum.de"
        or port not in {None, 443}
        or parts.username is not None
        or parts.password is not None
    ):
        raise MoodleError(ErrorCode.UNSAFE_URL, "Only TUM Moodle content can be fetched.")
    query = parse_qs(parts.query)
    if set(query) & {"sesskey", "action", "delete", "token", "wstoken"}:
        raise MoodleError(ErrorCode.UNSAFE_URL, "This link is not a read-only content URL.")
    if any(part in parts.path for part in ("/admin/", "/login/", "/attempt", "/edit")):
        raise MoodleError(ErrorCode.UNSAFE_URL, "This endpoint is not a content read.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def public_address() -> None:
    addresses = socket.getaddrinfo("www.moodle.tum.de", 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise MoodleError(ErrorCode.UNSAFE_URL, "Moodle resolved to a private network address.")


def cookie_jar(session: Session) -> httpx2.Cookies:
    cookies = httpx2.Cookies()
    for cookie in session.cookies:
        cookies.jar.set_cookie(
            JarCookie(
                version=0,
                name=cookie.name,
                value=cookie.value,
                port=None,
                port_specified=False,
                domain=cookie.domain,
                domain_specified=True,
                domain_initial_dot=cookie.domain.startswith("."),
                path=cookie.path,
                path_specified=True,
                secure=cookie.secure,
                expires=int(cookie.expires) if cookie.expires > 0 else None,
                discard=cookie.expires <= 0,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": cookie.httpOnly},
                rfc2109=False,
            )
        )
    return cookies


@dataclass(frozen=True, slots=True)
class Download:
    url: str
    content_type: str
    body: bytes
    etag: str
    modified: str

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class MoodleHTTP:
    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self._sesskey: str | None = None

    def get(self, url: str) -> Download:
        target = safe_url(url)
        return self._request(target)

    def read_api(self, method: str, arguments: dict[str, JsonValue]) -> JsonValue:
        allowed = {
            "core_course_get_enrolled_courses_by_timeline_classification",
            "core_course_get_contents",
            "mod_forum_get_forum_discussions",
            "mod_forum_get_discussion_posts",
            "core_message_get_conversations",
            "core_message_get_conversation_messages",
        }
        if method not in allowed:
            raise MoodleError(ErrorCode.UNSAFE_URL, "Only approved Moodle read APIs are allowed.")
        if self._sesskey is None:
            overview = self.get("/my/courses.php").text()
            key = re.search(r'"sesskey"\s*:\s*"([^"\\]+)"', overview)
            if key is None:
                raise MoodleError(ErrorCode.SESSION_EXPIRED, "Reconnect to TUM Moodle.")
            self._sesskey = key[1]
        payload = json.dumps([{"index": 0, "methodname": method, "args": arguments}])
        response = self._request(
            f"{BASE_URL}/lib/ajax/service.php?sesskey={self._sesskey}", "POST", payload
        )
        parsed = TypeAdapter(list[dict[str, JsonValue]]).validate_json(response.body)
        if not parsed or parsed[0].get("error"):
            raise MoodleError(
                ErrorCode.RESOURCE_UNSUPPORTED, "This Moodle read API is unavailable."
            )
        return parsed[0].get("data")

    def _request(
        self, target: str, method: Literal["GET", "POST"] = "GET", payload: str | None = None
    ) -> Download:
        session = self.store.load()
        deadline = time.monotonic() + 60
        try:
            with FileLock(self.store.paths.file("requests.lock"), timeout=60):
                public_address()
                with httpx2.Client(
                    cookies=cookie_jar(session),
                    follow_redirects=False,
                    timeout=httpx2.Timeout(30, connect=10),
                    limits=httpx2.Limits(max_connections=1, max_keepalive_connections=1),
                    http2=True,
                    headers={"User-Agent": "TUMMoodlePersonal/0.1"},
                ) as client:
                    result = self._read(client, target, deadline, method, payload)
                    updated = [
                        Cookie(
                            name=c.name,
                            value=c.value,
                            domain=c.domain,
                            path=c.path,
                            secure=c.secure,
                            expires=c.expires or -1,
                        )
                        for c in client.cookies.jar
                        if c.domain.lstrip(".") in {"moodle.tum.de", "www.moodle.tum.de"}
                    ]
                    self.store.save(session.model_copy(update={"cookies": updated}))
                    return result
        except (httpx2.HTTPError, socket.gaierror, TimeoutError, Timeout):
            raise MoodleError(
                ErrorCode.OFFLINE, "Could not reach Moodle; retry when online."
            ) from None

    def _read(
        self,
        client: httpx2.Client,
        target: str,
        deadline: float,
        method: Literal["GET", "POST"],
        payload: str | None,
    ) -> Download:
        for _hop in range(6):
            self._rate_limit()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MoodleError(ErrorCode.OFFLINE, "Moodle request exceeded its time limit.")
            with client.stream(
                method,
                target,
                content=payload,
                headers={"Content-Type": "application/json"} if payload else None,
                timeout=min(30, remaining),
            ) as response:
                if response.is_redirect:
                    location = urljoin(target, response.headers.get("location", ""))
                    if "/login/" in urlsplit(location).path:
                        raise MoodleError(ErrorCode.SESSION_EXPIRED, "Reconnect to TUM Moodle.")
                    target = safe_url(location)
                    continue
                if response.status_code in {401, 403}:
                    raise MoodleError(ErrorCode.ACCESS_DENIED, "This content is not accessible.")
                if response.status_code == 404:
                    raise MoodleError(ErrorCode.NOT_FOUND, "This Moodle resource was removed.")
                if response.status_code == 429:
                    retry = response.headers.get("retry-after", "")
                    message = f"Retry after {retry} seconds." if retry.isdigit() else "Retry later."
                    raise MoodleError(
                        ErrorCode.RATE_LIMITED, f"Moodle rate limit reached. {message}"
                    )
                if response.status_code >= 400:
                    raise MoodleError(ErrorCode.OFFLINE, "Moodle returned a server error.")
                content_type = response.headers.get("content-type", "").split(";")[0]
                if content_type.startswith(("video/", "audio/")):
                    return Download(target, content_type, b"", "", "")
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    if len(chunks) + len(chunk) > MAX_BYTES:
                        raise MoodleError(ErrorCode.TOO_LARGE, "Resource exceeds the 50 MiB limit.")
                    if time.monotonic() >= deadline:
                        raise MoodleError(ErrorCode.OFFLINE, "Moodle request timed out.")
                    chunks.extend(chunk)
                body = bytes(chunks)
                if "html" in content_type and (
                    b'id="login"' in body
                    or b'name="logintoken"' in body
                    or b"You are not logged in" in body
                ):
                    raise MoodleError(ErrorCode.SESSION_EXPIRED, "Reconnect to TUM Moodle.")
                return Download(
                    target,
                    content_type,
                    body,
                    response.headers.get("etag", ""),
                    response.headers.get("last-modified", ""),
                )
        raise MoodleError(ErrorCode.UNSAFE_URL, "Too many redirects.")

    def _rate_limit(self) -> None:
        path = self.store.paths.file("last-request")
        previous = float(path.read_text()) if path.exists() else 0
        wait = min(1, 1 - (time.time() - previous))
        if wait > 0:
            time.sleep(wait)
        private_write(path, str(time.time()).encode())
