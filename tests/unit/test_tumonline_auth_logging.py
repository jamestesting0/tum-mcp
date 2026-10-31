import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import hpack
import httpx2
import pytest
from httpcore2._trace import Trace

from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.auth import resume_session


def test_session_credentials_do_not_enter_http_debug_logs(caplog: pytest.LogCaptureFixture) -> None:
    cookie_value = "synthetic-cookie-secret"
    rotated_value = "synthetic-rotated-secret"
    access_value = "synthetic-token-secret"
    for name in ("httpcore2.http11", "httpcore2.http2", "hpack.hpack", "hpack.table"):
        caplog.set_level(logging.DEBUG, logger=name)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(201)
            self.send_header("Set-Cookie", f"session={rotated_value}; Path=/; Secure")
            self.end_headers()
            self.wfile.write(json.dumps({"accessToken": access_value}).encode())

        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"resource": [{"content": {"desktopProfileLibDto": {"obfuscatedId": "s"}}}]}
                ).encode()
            )

        def log_message(self, format: str, *args: str) -> None:
            pass

    class LocalTransport(httpx2.BaseTransport):
        def __init__(self, port: int) -> None:
            self.port = port
            self.inner = httpx2.HTTPTransport()

        def handle_request(self, request: httpx2.Request) -> httpx2.Response:
            # Exercise the real HTTP/2 header codec as well as an HTTP/1 transport.
            encoded = hpack.Encoder().encode([(b"authorization", access_value.encode())])
            hpack.Decoder().decode(encoded)
            table = hpack.table.HeaderTable()
            table.add(b"authorization", access_value.encode())
            table.maxsize = 0
            with Trace("receive_response_headers", logging.getLogger("httpcore2.http2")) as trace:
                trace.return_value = (200, [(b"set-cookie", rotated_value.encode())])
            local = httpx2.Request(
                request.method,
                f"http://127.0.0.1:{self.port}{request.url.raw_path.decode()}",
                headers=request.headers,
                content=request.content,
            )
            return self.inner.handle_request(local)

        def close(self) -> None:
            self.inner.close()

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            session, _ = resume_session(
                (Cookie(name="session", value=cookie_value, domain="campus.tum.de"),),
                LocalTransport(server.server_port),
            )
        finally:
            server.shutdown()
            thread.join()

    assert any(cookie.value == rotated_value for cookie in session.cookies)
    assert all(secret not in caplog.text for secret in (cookie_value, rotated_value, access_value))
