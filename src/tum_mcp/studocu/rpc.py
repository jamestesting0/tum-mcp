"""Bounded JSON-RPC replies, including complete events on a persistent SSE stream."""

from typing import Annotated, Literal

import httpx2
from pydantic import ConfigDict, Field, JsonValue, StrictBool, TypeAdapter

from tum_mcp.settings import Frozen

OBJECT = TypeAdapter(dict[str, JsonValue])


class ToolReply(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore")
    structuredContent: dict[str, JsonValue]
    isError: StrictBool = False


class Envelope(Frozen):
    model_config = ConfigDict(frozen=True, extra="ignore")
    jsonrpc: Literal["2.0"]
    id: Annotated[int, Field(strict=True, ge=1, le=1)]
    result: ToolReply
    error: None = None


def read_reply(response: httpx2.Response, limit: int) -> ToolReply:
    """Return the matching complete reply without waiting for SSE connection closure."""
    events = (
        response.headers.get("content-type", "").split(";", 1)[0].lower() == "text/event-stream"
    )
    body = bytearray()
    line = bytearray()
    fields: list[bytes] = []
    size = 0
    after_cr = False
    first_line = True
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > limit:
            raise ValueError("Reply exceeds its byte budget")
        if not events:
            body.extend(chunk)
            continue
        for byte in chunk:
            if after_cr and byte == 10:
                after_cr = False
                continue
            after_cr = False
            if byte not in {10, 13}:
                line.append(byte)
                continue
            after_cr = byte == 13
            field = bytes(line)
            line.clear()
            if first_line:
                field = field.removeprefix(b"\xef\xbb\xbf")
                first_line = False
            if field.startswith(b"data:"):
                fields.append(field[5:].removeprefix(b" "))
            elif not field and fields:
                payload = b"\n".join(fields)
                fields.clear()
                if not payload.strip():
                    continue
                message = OBJECT.validate_json(payload)
                if message.get("id") == 1:
                    return Envelope.model_validate(message).result
    if events:
        raise ValueError("Stream ended before its matching complete reply")
    return Envelope.model_validate_json(body).result
