"""Cookie-free scoped media GETs, byte limits, cancellation and safe failures."""

import ipaddress
import logging
import math
import re
import socket
import time
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Final
from urllib.parse import urlsplit

import httpx2
from pydantic import Field

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.media_budget import TransferBudget
from tum_mcp.lecture_processing.media_models import CacheEntry, MediaGrant, MediaRef
from tum_mcp.settings import Frozen

MAX_BODY: Final = 64 * 1024 * 1024


class RateLimit(CampusError):
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        super().__init__(Code.RATE_LIMITED, "Media rate limit reached after bounded retries.")


def _retry_after(value: str) -> float:
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            delay = 1
    return min(max(delay, 0), 30) if math.isfinite(delay) else 1


def _cookie_free(request: httpx2.Request) -> None:
    request.headers.pop("cookie", None)
    request.headers.pop("authorization", None)


class Transfer(Frozen):
    body: bytes = Field(default=b"", repr=False, exclude=True)
    unchanged: bool = False
    etag: str | None = None
    modified: str | None = None


class MediaHTTP:
    def __init__(
        self,
        grant: MediaGrant,
        budget: TransferBudget,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self.grant, self.budget, self.transport = grant, budget, transport
        self.client: httpx2.Client | None = None

    def __enter__(self) -> "MediaHTTP":
        # HTTP loggers must never emit a signed request URL, even under global DEBUG.
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        logging.getLogger("httpcore2").setLevel(logging.WARNING)
        transport = self.transport or httpx2.HTTPTransport(
            http2=True,
            retries=0,
            limits=httpx2.Limits(
                max_connections=4, max_keepalive_connections=4, keepalive_expiry=30
            ),
            socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
        )
        self.client = httpx2.Client(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx2.Timeout(30, connect=5, write=10, pool=10),
            headers={"Accept-Encoding": "identity"},
            event_hooks={"request": [_cookie_free]},
        )
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self.client is not None:
            self.client.close()

    def get(
        self, ref: MediaRef, previous: CacheEntry | None = None, *, limit: int = MAX_BODY
    ) -> Transfer:
        if not 1 <= limit <= MAX_BODY:
            raise CampusError(Code.SCOPE_DENIED, "Media response bound must be at most 64 MiB.")
        url = self.grant.resolve(ref.url.get_secret_value()).get_secret_value()
        ref = ref.model_copy(update={"url": self.grant.resolve(url)})
        if self.transport is None:
            self._public_host(url)
        for attempt in range(3):
            self.budget.check()
            try:
                return self._request(ref, previous, limit)
            except RateLimit as error:
                if attempt == 2:
                    raise
                delay = error.delay_s
            except CampusError as error:
                if error.code != Code.OFFLINE or attempt == 2:
                    raise
                delay = min(2**attempt, 30)
            if self.budget.cancelled.wait(delay):
                raise KeyboardInterrupt
        raise CampusError(Code.OFFLINE, "Media request failed within its retry bound.")

    def _public_host(self, url: str) -> None:
        try:
            addresses = socket.getaddrinfo(urlsplit(url).hostname, 443, type=socket.SOCK_STREAM)
            if not addresses or any(
                not ipaddress.ip_address(item[4][0]).is_global
                or ipaddress.ip_address(item[4][0]).is_multicast
                for item in addresses
            ):
                raise CampusError(
                    Code.SCOPE_DENIED, "Private-network media destinations are disabled."
                )
        except (socket.gaierror, ValueError):
            raise CampusError(Code.OFFLINE, "Media host resolution failed; URL omitted.") from None

    def _request(self, ref: MediaRef, previous: CacheEntry | None, limit: int) -> Transfer:
        if self.client is None:
            raise CampusError(Code.ACTION_REQUIRED, "Open the media client before retrieval.")
        headers: dict[str, str] = {}
        if ref.byte_range:
            headers["Range"] = ref.byte_range.header
        if previous is not None:
            if previous.etag:
                headers["If-None-Match"] = previous.etag
            elif previous.modified:
                headers["If-Modified-Since"] = previous.modified
        try:
            with self.client.stream("GET", ref.url.get_secret_value(), headers=headers) as response:
                if response.status_code == 304 and previous is not None:
                    return Transfer(unchanged=True)
                if response.is_redirect:
                    raise CampusError(
                        Code.SCOPE_DENIED, "Media redirect is outside the approved capability."
                    )
                if response.status_code in {401, 403}:
                    raise CampusError(
                        Code.AUTH_REQUIRED,
                        "Media capability expired; refresh authorized metadata once.",
                    )
                if response.status_code == 429:
                    raise RateLimit(_retry_after(response.headers.get("retry-after", "1")))
                if response.status_code >= 500:
                    raise CampusError(Code.OFFLINE, "Media service is temporarily unavailable.")
                if response.status_code not in {200, 206}:
                    raise CampusError(
                        Code.CAPABILITY_UNSUPPORTED, f"Media returned HTTP {response.status_code}."
                    )
                if response.headers.get("content-length"):
                    try:
                        if not 0 <= int(response.headers["content-length"]) <= limit:
                            raise CampusError(
                                Code.INVALID_RESPONSE, "Media response exceeds its byte bound."
                            )
                    except ValueError:
                        raise CampusError(
                            Code.INVALID_RESPONSE, "Invalid media response length."
                        ) from None
                body = bytearray()
                for chunk in response.iter_bytes():
                    self.budget.check()
                    self.budget.charge(len(chunk))
                    if len(body) + len(chunk) > limit:
                        raise CampusError(
                            Code.INVALID_RESPONSE, "Media response exceeds its byte bound."
                        )
                    body.extend(chunk)
                if not body:
                    raise CampusError(Code.INVALID_RESPONSE, "Empty media response.")
                if (
                    "content-length" in response.headers
                    and "content-encoding" not in response.headers
                    and int(response.headers["content-length"]) != len(body)
                ):
                    raise CampusError(
                        Code.INVALID_RESPONSE, "Media response ended before its declared length."
                    )
                if ref.byte_range:
                    size, offset = ref.byte_range.length, ref.byte_range.offset
                    if response.status_code == 206:
                        match = re.fullmatch(
                            r"bytes (\d+)-(\d+)/(?:\d+|\*)",
                            response.headers.get("content-range", ""),
                        )
                        if (
                            match is None
                            or int(match[1]) != offset
                            or int(match[2]) != offset + size - 1
                            or len(body) != size
                        ):
                            raise CampusError(
                                Code.INVALID_RESPONSE, "Media byte range did not match the request."
                            )
                    else:
                        if len(body) < offset + size:
                            raise CampusError(
                                Code.INVALID_RESPONSE, "Ignored Range response is incomplete."
                            )
                        body = body[offset : offset + size]
                elif response.status_code == 206:
                    raise CampusError(Code.INVALID_RESPONSE, "Unexpected partial media response.")
                etag, modified = response.headers.get("etag"), response.headers.get("last-modified")
                return Transfer(
                    body=bytes(body),
                    etag=etag if etag and len(etag) <= 512 else None,
                    modified=modified if modified and len(modified) <= 512 else None,
                )
        except httpx2.HTTPError:
            raise CampusError(
                Code.OFFLINE, "Media transfer failed; credentials and URL omitted."
            ) from None
