import json
import os
import socket
import struct
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx2
from study_comments_data import operation

from tum_mcp.study_preview import Handler


def test_comment_endpoint_is_same_origin_bounded_and_confined(project: Path) -> None:
    first = operation(project)
    with ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "study"))
    ) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            endpoint = base + "/_study/comments"
            with httpx2.Client(trust_env=False, timeout=3) as client:
                current = client.get(endpoint)
                assert current.status_code == 200
                assert current.json()["comments"] == []
                etag = current.headers["etag"]
                cached = client.get(endpoint, headers={"If-None-Match": etag})
                assert cached.status_code == 304 and cached.content == b""
                assert cached.headers["etag"] == etag
                assert (
                    client.get(
                        endpoint,
                        headers={"If-None-Match": etag, "Origin": "https://attacker.invalid"},
                    ).status_code
                    == 403
                )
                assert "access-control-allow-origin" not in current.headers
                body = first.model_dump(mode="json")
                for headers in (
                    {},
                    {"Origin": "null"},
                    {"Origin": "https://attacker.invalid"},
                    {"Origin": base, "Sec-Fetch-Site": "cross-site"},
                    {"Origin": base, "Host": "attacker.invalid"},
                ):
                    assert client.post(endpoint, json=body, headers=headers).status_code == 403
                assert not (project / ".tum-mcp/comments.json").exists()
                assert (
                    client.post(
                        endpoint,
                        content="{}",
                        headers={"Origin": base, "Content-Type": "text/plain"},
                    ).status_code
                    == 415
                )
                assert (
                    client.post(
                        endpoint,
                        content="x" * 70000,
                        headers={"Origin": base, "Content-Type": "application/json"},
                    ).status_code
                    == 413
                )
                invalid = body | {"path": "../AGENTS.md"}
                assert (
                    client.post(endpoint, json=invalid, headers={"Origin": base}).status_code == 400
                )
                good = client.post(endpoint, json=body, headers={"Origin": base})
                assert good.status_code == 200
                assert good.json()["comments"][0]["text"] == first.text
                changed = client.get(endpoint, headers={"If-None-Match": etag})
                assert changed.status_code == 200 and changed.headers["etag"] != etag
                assert changed.headers["etag"] == good.headers["etag"]
                assert client.post(endpoint, json=body, headers={"Origin": base}).status_code == 409
                assert (
                    client.post(
                        base + "/content.json", json={}, headers={"Origin": base}
                    ).status_code
                    == 404
                )
                assert client.get(base + "/../.tum-mcp/comments.json").status_code == 404
                assert json.loads((project / ".tum-mcp/comments.json").read_bytes())["comments"][0][
                    "id"
                ] == str(first.id)
        finally:
            server.shutdown()
            worker.join(timeout=2)
            assert not worker.is_alive(), "Comment test server did not stop."


def test_rejected_post_keeps_its_response_when_the_body_arrives_late(tmp_path: Path) -> None:
    # An HTTP client may still be sending when origin/size checks reject its headers.
    site = tmp_path / "study"
    site.mkdir()

    class AbortiveCloseServer(ThreadingHTTPServer):
        def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
            connection, address = super().get_request()
            # Expose the Windows early-close reset on every test host. A graceful
            # write shutdown must deliver the response before this final close.
            linger = struct.pack("HH" if os.name == "nt" else "ii", 1, 0)
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
            return connection, address

    with AbortiveCloseServer(("127.0.0.1", 0), partial(Handler, directory=str(site))) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for size, origin, status in [
                (20000, "https://attacker.invalid", 403),
                (70000, None, 413),
            ]:
                base = f"http://127.0.0.1:{server.server_port}"
                headers = (
                    f"POST /_study/comments HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                    f"Origin: {origin or base}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {size}\r\nConnection: close\r\n\r\n"
                )
                with socket.create_connection(("127.0.0.1", server.server_port), timeout=3) as peer:
                    peer.sendall(headers.encode("ascii") + b"x" * 256)
                    with peer.makefile("rb") as response:
                        assert int(response.readline().split()[1]) == status
                        length = None
                        while line := response.readline():
                            if line == b"\r\n":
                                break
                            if line.lower().startswith(b"content-length:"):
                                length = int(line.split(b":", 1)[1])
                        assert length is not None
                        # Complete the body after the rejection. A hard close with
                        # unread bytes loses the response through a TCP reset.
                        peer.sendall(b"x" * (size - 256))
                        peer.shutdown(socket.SHUT_WR)
                        assert len(response.read(length)) == length
                        assert response.read(1) == b""
            assert not (tmp_path / ".tum-mcp").exists()
        finally:
            server.shutdown()
            worker.join(timeout=2)
            assert not worker.is_alive()
