import base64
import hashlib

from pydantic import JsonValue

from tum_moodle.errors import ErrorCode, MoodleError
from tum_moodle.models import Extracted


def offset_of(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isascii() or not cursor.isdecimal() or len(cursor) > 7:
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Invalid pagination cursor.")
    return int(cursor)


def excerpt(
    extracted: Extracted,
    cursor: str | None,
    max_chars: int,
    start_page: int | None,
    end_page: int | None,
) -> dict[str, JsonValue]:
    if cursor and (start_page is not None or end_page is not None):
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Use a cursor or page range, not both.")
    if start_page and end_page and start_page > end_page:
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "The page range is reversed.")
    fingerprint = hashlib.sha256(extracted.model_dump_json().encode()).hexdigest()[:16]
    offset = 0
    if cursor:
        try:
            digest, low, high, position = base64.urlsafe_b64decode(cursor).decode().split(":")
            offset = int(position)
            start_page, end_page = int(low) or None, int(high) or None
            if digest != fingerprint or offset < 0:
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            raise MoodleError(
                ErrorCode.RESOURCE_UNSUPPORTED, "Cursor is invalid or content changed."
            ) from None
    pages = [
        page
        for page in extracted.pages
        if (start_page is None or page.number >= start_page)
        and (end_page is None or page.number <= end_page)
    ]
    if not pages and (start_page is not None or end_page is not None):
        raise MoodleError(
            ErrorCode.RESOURCE_UNSUPPORTED,
            f"Requested range is outside this document's {len(extracted.pages)} page(s).",
        )
    total = sum(len(page.text) for page in pages)
    result: list[JsonValue] = []
    remaining = max_chars
    skipped = 0
    for page in pages:
        if skipped + len(page.text) <= offset:
            skipped += len(page.text)
            continue
        start = max(0, offset - skipped)
        text = page.text[start : start + remaining]
        result.append({"number": page.number, "unit": page.unit, "text": text})
        remaining -= len(text)
        skipped += len(page.text)
        if remaining <= 0 or len(result) >= 50:
            break
    following = offset + max_chars - remaining
    token = base64.urlsafe_b64encode(
        f"{fingerprint}:{start_page or 0}:{end_page or 0}:{following}".encode()
    ).decode()
    return {
        "pages": result,
        "total_pages": len(extracted.pages),
        "warnings": list(extracted.warnings),
        "next_cursor": token if following < total else None,
    }
