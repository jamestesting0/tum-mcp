"""Private, recording-scoped media grants and credential-free segment identities."""

import hashlib
import posixpath
from typing import Annotated, Final
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit

from pydantic import Field, SecretStr

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.settings import Frozen

MAX_PLAYLIST_BYTES: Final = 4 * 1024 * 1024


class ByteRange(Frozen):
    offset: int = Field(ge=0, le=1 << 40)
    length: int = Field(gt=0, le=64 * 1024 * 1024)

    @property
    def header(self) -> str:
        return f"bytes={self.offset}-{self.offset + self.length - 1}"


class MediaRef(Frozen):
    url: SecretStr = Field(repr=False, exclude=True)
    byte_range: ByteRange | None = None

    @property
    def key(self) -> str:
        parts = urlsplit(self.url.get_secret_value())
        stable_query = urlencode(
            sorted(
                (key, value)
                for key, value in parse_qsl(parts.query)
                if not any(
                    word in key.lower()
                    for word in ("jwt", "token", "sign", "expires", "x-amz", "policy", "key-pair")
                )
            )
        )
        identity = f"{parts.scheme}://{parts.netloc}{parts.path}?{stable_query}\0{self.byte_range}"
        return hashlib.sha256(identity.encode()).hexdigest()


class MediaGrant(Frozen):
    """Only created from the authenticated, membership-verified watch view capability."""

    playlist: SecretStr = Field(repr=False, exclude=True)

    @property
    def origin(self) -> str:
        parts = urlsplit(self.playlist.get_secret_value())
        return f"{parts.scheme}://{parts.netloc}"

    def resolve(self, uri: str) -> SecretStr:
        base = self.playlist.get_secret_value().replace("{{quality}}", "")
        try:
            value = urljoin(base, uri)
            parts, original = urlsplit(value), urlsplit(base)
            decoded = unquote(parts.path)
            port = parts.port
        except ValueError:
            raise CampusError(Code.SCOPE_DENIED, "Media URI has an invalid authority.") from None
        scope = posixpath.dirname(original.path).rstrip("/") + "/"
        if (
            len(value) > 8000
            or parts.scheme != "https"
            or not parts.hostname
            or port not in {None, 443}
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or f"{parts.scheme}://{parts.netloc}" != self.origin
            or "\\" in decoded
            or any(ord(c) < 32 for c in value)
            or any(token in parts.path.lower() for token in ("%2e", "%2f", "%5c", "%25"))
            or ".." in decoded.split("/")
            or not posixpath.normpath(decoded).startswith(scope)
        ):
            raise CampusError(
                Code.SCOPE_DENIED, "Media URI leaves the verified recording capability."
            )
        return SecretStr(value)


class Segment(Frozen):
    sequence: int = Field(ge=0)
    span: Interval
    media: MediaRef
    initialization: MediaRef | None = None
    discontinuity: int = Field(default=0, ge=0)


class Manifest(Frozen):
    segments: tuple[Segment, ...] = Field(min_length=1, max_length=10000)

    @property
    def duration_s(self) -> float:
        return self.segments[-1].span.end_s

    @property
    def revision(self) -> str:
        identity = "\n".join(
            f"{s.sequence}:{s.span}:{s.media.key}:"
            f"{s.initialization.key if s.initialization else ''}:{s.discontinuity}"
            for s in self.segments
        )
        return hashlib.sha256(identity.encode()).hexdigest()


class CacheEntry(Frozen):
    key: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    size: int = Field(ge=0, le=64 * 1024 * 1024)
    etag: str | None = Field(default=None, max_length=512, repr=False)
    modified: str | None = Field(default=None, max_length=512, repr=False)
