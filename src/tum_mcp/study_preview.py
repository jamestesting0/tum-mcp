"""Loopback course preview with a confined, same-origin passage-comment endpoint."""

import errno
import gzip
import io
import json
import re
import shutil
import socket
import subprocess
import time
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlsplit

import typer

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import is_wsl
from tum_mcp.study_store import confined


class PreviewServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits simultaneous listeners, unlike POSIX reuse.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")
    allow_reuse_port = False
    # The app requests ~30 modules at once; Windows refuses connections beyond the
    # listen backlog (default 5) instead of queueing them, so the course fails to load.
    request_queue_size = 128

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


VIDEO_FOLDERS = frozenset({"tracks", "captions", "chapters", "posters", "narration"})
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".vtt": "text/vtt; charset=utf-8",
    ".jpg": "image/jpeg",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
}
VIDEO_NAME = re.compile(r"[0-9a-z][0-9a-z_.-]{0,120}")
RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class Slice:
    """Read at most `length` bytes of a file from `start`, for a single byte-range reply."""

    def __init__(self, stream: BinaryIO, start: int, length: int) -> None:
        stream.seek(start)
        self.stream, self.remaining = stream, length

    def read(self, size: int = -1) -> bytes:
        size = self.remaining if size < 0 else min(size, self.remaining)
        data = self.stream.read(size) if size else b""
        self.remaining -= len(data)
        return data

    def close(self) -> None:
        self.stream.close()


def byte_range(header: str | None, size: int) -> tuple[int, int] | None | bool:
    """(start, end) for one satisfiable range, None to send everything, False if unsatisfiable."""
    if not header or "," in header:
        return None
    match = RANGE.fullmatch(header.strip())
    if match is None or not (match[1] or match[2]):
        return None
    if match[1]:
        start = int(match[1])
        if match[2] and int(match[2]) < start:
            return None
        end = min(int(match[2]), size - 1) if match[2] else size - 1
    else:
        start, end = max(0, size - int(match[2])), size - 1
        if int(match[2]) == 0:
            return False
    return (start, end) if start < size and start <= end else False


class Handler(SimpleHTTPRequestHandler):
    # OS file associations (notably Windows .mjs entries) are not web MIME types.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".woff2": "font/woff2",
    }

    def finish(self) -> None:
        # Early HTTP rejections can leave an in-flight body unread. A hard close
        # then resets Windows TCP and discards the response. Send FIN first and
        # drain only a bounded amount/time before the ordinary socket cleanup.
        try:
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_WR)
            budget = 128 * 1024
            deadline = time.monotonic() + 0.5
            while budget and (remaining := deadline - time.monotonic()) > 0:
                self.connection.settimeout(remaining)
                chunk = self.connection.recv(min(16384, budget))
                if not chunk:
                    break
                budget -= len(chunk)
        except OSError:
            pass  # A disconnected or stalled peer must not prevent cleanup.
        finally:
            super().finish()

    def do_GET(self) -> None:
        from tum_mcp.study_comment_api import ENDPOINT, comments_request

        if self.path == ENDPOINT:
            comments_request(self, self.directory, write=False)
        else:
            super().do_GET()

    def do_POST(self) -> None:
        from tum_mcp.study_comment_api import ENDPOINT, comments_request

        if self.path == ENDPOINT:
            comments_request(self, self.directory, write=True)
        else:
            self.send_error(404)

    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; media-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Accept-Encoding")
        super().end_headers()

    def log_message(self, format: str, *args: str) -> None:
        return

    def video_head(self) -> BinaryIO | Slice | None:
        return _video_reply(self)

    def list_directory(self, path: str) -> None:
        self.send_error(404)
        return None

    def send_head(self) -> BinaryIO | Slice | None:
        allowed = {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }
        host = self.headers.get("Host", "")
        if host not in allowed or self.headers.get("Origin", f"http://{host}") not in {
            f"http://{value}" for value in allowed
        }:
            self.send_error(403)
            return None
        if urlsplit(self.path).path.startswith("/videos/"):
            return self.video_head()
        base = Path(self.directory).resolve()
        target = Path(self.translate_path(self.path))
        try:
            relative = target.relative_to(base)
            confined(base, relative.as_posix())
        except (ValueError, CampusError):
            self.send_error(404)
            return None
        if any(part.startswith(".") for part in relative.parts):
            self.send_error(404)
            return None
        encodings = {
            part.strip().lower() for part in self.headers.get("Accept-Encoding", "").split(",")
        }
        if "gzip" in encodings and target.suffix in {".css", ".mjs", ".html"}:
            try:
                if target.is_file() and target.stat().st_size <= 4 * 1024 * 1024:
                    raw = target.read_bytes()
                    body = gzip.compress(raw, compresslevel=5, mtime=0)
                    if len(body) < len(raw):
                        self.send_response(200)
                        self.send_header("Content-Type", self.guess_type(str(target)))
                        self.send_header("Content-Encoding", "gzip")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        return io.BytesIO(body)
            except OSError:
                return super().send_head()
        return super().send_head()


def _video_reply(handler: "Handler") -> BinaryIO | Slice | None:
    path = unquote(urlsplit(handler.path).path)
    project = Path(handler.directory).resolve().parent
    if path == "/videos/index.json":
        from tum_mcp.video_project import preview_index

        body = json.dumps(preview_index(project)).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        return io.BytesIO(body)
    parts = path.split("/")[2:]
    if (
        len(parts) != 2
        or parts[0] not in VIDEO_FOLDERS
        or VIDEO_NAME.fullmatch(parts[1]) is None
        or Path(parts[1]).suffix not in VIDEO_TYPES
    ):
        handler.send_error(404)
        return None
    try:
        target = confined(project, f"videos/{parts[0]}/{parts[1]}")
        if not target.is_file():
            raise CampusError(Code.WORKSPACE_CONFLICT, "missing")
        stream = target.open("rb")
    except (CampusError, OSError):
        handler.send_error(404)
        return None
    size = target.stat().st_size
    span = byte_range(handler.headers.get("Range"), size)
    if span is False:
        stream.close()
        handler.send_response(416)
        handler.send_header("Content-Range", f"bytes */{size}")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return None
    handler.send_response(200 if span is None else 206)
    handler.send_header("Content-Type", VIDEO_TYPES[target.suffix])
    handler.send_header("Accept-Ranges", "bytes")
    if span is None:
        handler.send_header("Content-Length", str(size))
        handler.end_headers()
        return stream
    start, end = span
    handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.send_header("Content-Length", str(end - start + 1))
    handler.end_headers()
    return Slice(stream, start, end - start + 1)


def serve(project: Path, port: int, *, open_browser: bool = False) -> None:
    root = project.expanduser().resolve()
    site = app_path(root, "index.html").parent
    if not (site / "index.html").is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Build the study site first.")
    try:
        server = PreviewServer(("127.0.0.1", port), partial(Handler, directory=str(site)))
    except OSError as error:
        # Winsock exposes its native code instead of the POSIX errno.
        if error.errno not in {errno.EADDRINUSE, 10048}:
            raise
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Port {port} is in use. Stop the other preview or run tum-mcp study --port PORT "
            "with a different port. Keep the same port to retain browser progress.",
        ) from None
    with server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Study preview: {url}", flush=True)
        from tum_mcp.study_publish_models import load_publication

        try:
            publication = load_publication(root)
            if publication is not None:
                if publication.hosted_url:
                    print(f"Hosted study: {publication.hosted_url}", flush=True)
                print(f"GitHub repository: https://github.com/{publication.repository}", flush=True)
                if publication.deployed_commit != publication.commit:
                    print("Latest hosted update is pending verification.", flush=True)
                if not publication.auto_sync:
                    print("Automatic publication is paused.", flush=True)
        except CampusError:
            print(
                "Saved GitHub publication settings need review; local preview is available.",
                flush=True,
            )
        try:
            if open_browser:
                try:
                    if is_wsl():
                        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
                        opened = (
                            shell is not None
                            and subprocess.run(  # noqa: S603
                                [
                                    shell,
                                    "-NoProfile",
                                    "-NonInteractive",
                                    "-Command",
                                    f"Start-Process '{url}'",
                                ],
                                capture_output=True,
                                timeout=10,
                                check=False,
                            ).returncode
                            == 0
                        )
                    else:
                        opened = typer.launch(url) == 0
                except (OSError, subprocess.SubprocessError, webbrowser.Error):
                    opened = False
                if not opened:
                    print("Open the URL above in your browser.", flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            print("Study preview stopped.")
