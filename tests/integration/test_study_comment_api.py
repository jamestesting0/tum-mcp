import json
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
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            endpoint = base + "/_study/comments"
            with httpx2.Client(trust_env=False) as client:
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
                assert not (project / ".study/comments.json").exists()
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
                assert client.get(base + "/../.study/comments.json").status_code == 404
                assert json.loads((project / ".study/comments.json").read_bytes())["comments"][0][
                    "id"
                ] == str(first.id)
        finally:
            server.shutdown()
