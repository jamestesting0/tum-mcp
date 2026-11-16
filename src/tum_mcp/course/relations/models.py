"""Request purposes, text normalization and canonical digests for course links."""

import json
import unicodedata
from typing import Literal

from pydantic import JsonValue

from tum_mcp.course.project.store import digest

Purpose = Literal["study", "lectures", "exercises", "exam", "review"]


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip()


def canonical_digest(value: JsonValue) -> str:
    return digest(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    )
