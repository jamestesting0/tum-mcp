"""The preview's only write surface: bounded same-origin comment operations."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_comment_models import OPERATION
from tum_mcp.study_comments import change_comment, read_comments

ENDPOINT = "/_study/comments"


def same_origin(handler: BaseHTTPRequestHandler, *, require_origin: bool = False) -> bool:
    port = cast(HTTPServer, handler.server).server_port
    host = handler.headers.get("Host", "")
    if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
        return False
    origin = handler.headers.get("Origin")
    if origin is not None and origin != f"http://{host}":
        return False
    if require_origin and origin is None:
        return False
    return handler.headers.get("Sec-Fetch-Site", "same-origin") in {"same-origin", "none"}


def reply(
    handler: BaseHTTPRequestHandler, status: int, value: dict, etag: str | None = None
) -> None:
    body = b"" if status == 304 else json.dumps(value, ensure_ascii=True).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    if status != 304:
        handler.send_header("Content-Length", str(len(body)))
    if etag is not None:
        handler.send_header("ETag", etag)
    handler.end_headers()
    handler.wfile.write(body)


def comments_request(handler: BaseHTTPRequestHandler, directory: str, *, write: bool) -> None:
    if not same_origin(handler, require_origin=write):
        reply(handler, 403, {"error": "Comments require the local preview origin."})
        return
    try:
        root = Path(directory).resolve().parent
        if write:
            size = int(handler.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536 or handler.headers.get("Transfer-Encoding"):
                reply(handler, 413, {"error": "Comment request is too large or incomplete."})
                return
            if handler.headers.get_content_type() != "application/json":
                reply(handler, 415, {"error": "Comment requests require JSON."})
                return
            operation = OPERATION.validate_json(handler.rfile.read(size))
            value = change_comment(root, operation)
        else:
            value = read_comments(root)
        etag = f'"{value["revision"]}"'
        unchanged = not write and handler.headers.get("If-None-Match") == etag
        reply(handler, 304 if unchanged else 200, value, etag)
    except (ValueError, ValidationError):
        reply(handler, 400, {"error": "Invalid comment request; no changes saved."})
    except CampusError as error:
        status = 403 if error.code == Code.SCOPE_DENIED else 409
        reply(handler, status, {"error": error.message})
    except OSError:
        reply(
            handler, 503, {"error": "Comments could not be saved. Check project access and retry."}
        )
