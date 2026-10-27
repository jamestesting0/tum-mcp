import mimetypes
import socket
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx2
import pytest

from tum_mcp.study_preview import Handler, PreviewServer


def test_loopback_preview_confines_files_and_rejects_foreign_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows registry associations must not decide whether ES modules can run.
    mimetypes.init()
    monkeypatch.setitem(mimetypes.types_map, ".mjs", "text/plain")
    site = tmp_path / "study"
    site.mkdir()
    (site / "index.html").write_text("<!doctype html><title>Course</title>", encoding="utf-8")
    (site / "app.mjs").write_bytes(b"export default 42;\n")
    css = "body { color: navy; }\n" * 200
    (site / "styles.css").write_bytes(css.encode("utf-8"))
    (site / ".managed.json").write_text("private build metadata", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("outside study", encoding="utf-8")
    (site / "folder").mkdir()
    linked = False
    try:
        (site / "linked.txt").symlink_to(tmp_path / "AGENTS.md")
        linked = True
    except OSError:
        pass  # Native Windows may not grant creation of test symlinks.
    with ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(site))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with httpx2.Client(trust_env=False, timeout=3) as client:
                good = client.get(base + "/")
                assert good.status_code == 200
                module = client.get(base + "/app.mjs")
                assert module.headers["content-type"].split(";")[0] == "text/javascript"
                assert "default-src 'self'" in good.headers["content-security-policy"]
                assert good.headers["referrer-policy"] == "no-referrer"
                compressed = client.get(base + "/styles.css", headers={"Accept-Encoding": "gzip"})
                assert compressed.text == css and compressed.headers["content-encoding"] == "gzip"
                assert int(compressed.headers["content-length"]) < len(css)
                assert compressed.headers["vary"] == "Accept-Encoding"
                head = client.head(base + "/styles.css", headers={"Accept-Encoding": "gzip"})
                assert (
                    head.content == b""
                    and head.headers["content-length"] == compressed.headers["content-length"]
                )
                for encoding in ("identity", "gzip;q=0"):
                    plain = client.get(base + "/styles.css", headers={"Accept-Encoding": encoding})
                    assert plain.text == css and "content-encoding" not in plain.headers
                for path in ("/.managed.json", "/folder/", "/../AGENTS.md", "/%2e%2e/AGENTS.md"):
                    response = client.get(base + path)
                    assert response.status_code == 404, (path, response.status_code)
                if linked:
                    assert client.get(base + "/linked.txt").status_code == 404
                assert client.get(base, headers={"Host": "attacker.invalid"}).status_code == 403
                assert (
                    client.get(base, headers={"Origin": "https://attacker.invalid"}).status_code
                    == 403
                )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive(), "Preview test server did not stop."


def test_preview_queues_the_apps_parallel_module_burst(tmp_path: Path) -> None:
    # The app opens ~30 module requests at once. A listen backlog of 5 makes Windows
    # refuse the rest (and others stall), which shows "Course unavailable".
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(tmp_path))) as server:
        port = server.server_address[1]
        clients = [socket.create_connection(("127.0.0.1", port), timeout=5) for _ in range(40)]
        for client in clients:
            client.close()
