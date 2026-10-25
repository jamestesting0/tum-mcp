"""A loopback-only, static course preview. No source directories or directory listings."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_store import confined


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: str) -> None:
        return

    def list_directory(self, path: str) -> None:
        self.send_error(404)
        return None

    def send_head(self) -> BinaryIO | None:
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
        return super().send_head()


def serve(project: Path, port: int) -> None:
    root = project.expanduser().resolve()
    site = confined(root, "study")
    if not confined(root, "study/index.html").is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Build the study site first.")
    with ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(site))) as server:
        print(f"Study preview: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Study preview stopped.")
