"""Short-lived cursors bound to an account, its policy and the request shape."""

import base64
import binascii
import hashlib
import hmac
import re
import secrets
import time
from typing import Final, Literal

from pydantic import Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

LIFETIME: Final = 3600
CURSOR_PATTERN: Final = re.compile(r"[A-Za-z0-9_-]{1,512}")


class CursorBinding(Frozen):
    account_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(ge=0, strict=True)
    limit: int = Field(ge=1, le=100, strict=True)
    operation: Literal["courses", "curriculum_positions"] = "courses"
    course_id: int | None = Field(default=None, gt=0, strict=True)


class CursorPayload(Frozen):
    binding: CursorBinding
    offset: int = Field(ge=0, le=100000, strict=True)
    expires: int = Field(ge=0, strict=True)


class CursorCodec:
    def __init__(self, key: bytes | None = None) -> None:
        self._key = key if key is not None else secrets.token_bytes(32)

    def encode(self, binding: CursorBinding, *, offset: int, now: int | None = None) -> str:
        current = int(time.time()) if now is None else now
        try:
            body = CursorPayload(binding=binding, offset=offset, expires=current + LIFETIME)
        except ValidationError:
            raise CampusError(Code.SCOPE_DENIED, "Invalid TUMonline page cursor.") from None
        data = body.model_dump_json().encode()
        signature = hmac.new(self._key, data, hashlib.sha256).hexdigest().encode()
        return base64.urlsafe_b64encode(data + b"." + signature).decode().rstrip("=")

    def decode(self, token: str, binding: CursorBinding, *, now: int | None = None) -> int:
        if not CURSOR_PATTERN.fullmatch(token):
            raise CampusError(Code.SCOPE_DENIED, "Invalid TUMonline page cursor.")
        try:
            packed = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            data, signature = packed.rsplit(b".", 1)
            expected = hmac.new(self._key, data, hashlib.sha256).hexdigest().encode()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = CursorPayload.model_validate_json(data)
        except (ValueError, binascii.Error, ValidationError):
            raise CampusError(Code.SCOPE_DENIED, "Invalid TUMonline page cursor.") from None
        current = int(time.time()) if now is None else now
        if payload.binding != binding or current >= payload.expires:
            raise CampusError(Code.STALE_RESULT, "TUMonline page cursor has expired or changed.")
        return payload.offset
