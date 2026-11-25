"""Synthetic GitHub wire boundary; no account, credentials or network are used."""

import base64
import hashlib
import json
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from threading import Thread

from pydantic import JsonValue

from tum_mcp.course.app.preview import PreviewServer, byte_range
from tum_mcp.course.app.publish_site import blob_sha


class PagesHandler(SimpleHTTPRequestHandler):
    """A static host that answers one byte range, as GitHub Pages does for media."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
        ".m4a": "audio/mp4",
        ".vtt": "text/vtt",
    }

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def send_head(self):  # noqa: ANN201 - returns the body stream like the base class
        path = Path(self.translate_path(self.path))
        if not path.is_file() or "Range" not in self.headers:
            return super().send_head()
        size = path.stat().st_size
        span = byte_range(self.headers["Range"], size)
        if not isinstance(span, tuple):
            return super().send_head()
        start, end = span
        with path.open("rb") as stream:
            _ = stream.seek(start)
            body = stream.read(end - start + 1)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return BytesIO(body)


@contextmanager
def serve_export(site: dict[str, bytes], directory: Path) -> Iterator[str]:
    """Write a public export and serve it the way a Pages site would."""
    for name, value in site.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    handler = partial(PagesHandler, directory=str(directory))
    with PreviewServer(("127.0.0.1", 0), handler) as server:
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()


@dataclass(frozen=True, slots=True)
class Request:
    method: str
    endpoint: str
    body: JsonValue


class GitHubFixture:
    """Mutable in-memory Git database and Pages service for end-to-end CLI tests."""

    def __init__(self) -> None:
        self.requests: list[Request] = []
        self.repositories: dict[str, dict] = {}
        self.trees: dict[str, dict[str, bytes]] = {}
        self.commits: dict[str, dict] = {}
        self.pages: dict[str, dict] = {}
        self.blobs: dict[str, bytes] = {}
        self.build_status = "built"
        self.build_commit: str | None = None
        self.check_status = "completed"
        self.check_conclusion = "success"
        self.workflow_status = "completed"
        self.plan_eligible = True
        self.authentication = True
        self.concurrent_push = False
        self.lose_creation_response = False
        self.timeouts: list[int] = []
        # Blob uploads fail after this many, as if the network dropped mid-publication.
        self.upload_limit: int | None = None

    def known(self, sha: str) -> bytes | None:
        if sha in self.blobs:
            return self.blobs[sha]
        found = (value for tree in self.trees.values() for value in tree.values())
        return next((value for value in found if blob_sha(value) == sha), None)

    def tree(self, files: dict[str, bytes]) -> str:
        sha = hashlib.sha1(
            json.dumps({key: value.hex() for key, value in files.items()}, sort_keys=True).encode(),
            usedforsecurity=False,
        ).hexdigest()
        self.trees[sha] = dict(files)
        return sha

    def commit(self, tree: str, parents: list[str]) -> str:
        sha = hashlib.sha1(json.dumps([tree, parents]).encode(), usedforsecurity=False).hexdigest()
        self.commits[sha] = {"sha": sha, "tree": {"sha": tree}, "parents": parents}
        return sha

    def create(self, name: str) -> dict[str, JsonValue]:
        tree = self.tree({"README.md": b"Synthetic generated study repository\n"})
        self.repositories[name] = {
            "full_name": name,
            "private": True,
            "default_branch": "main",
            "head": self.commit(tree, []),
        }
        return self.repositories[name]

    def files(self, name: str) -> dict[str, bytes]:
        head = self.repositories[name]["head"]
        return self.trees[self.commits[head]["tree"]["sha"]]

    def edit(self, name: str, path: str, content: bytes) -> None:
        remote = self.repositories[name]
        files = {**self.files(name), path: content}
        remote["head"] = self.commit(self.tree(files), [remote["head"]])

    def run(
        self,
        arguments: list[str],
        *,
        input: bytes | None,
        capture_output: bool,
        timeout: int,
        check: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[bytes]:
        assert arguments[:4] == ["/synthetic/gh", "api", "--hostname", "github.com"]
        assert capture_output and timeout >= 45 and not check
        self.timeouts.append(timeout)
        assert "GH_DEBUG" not in env and env["GH_PROMPT_DISABLED"] == "1"
        method = arguments[arguments.index("--method") + 1]
        endpoint = arguments[8]
        body = json.loads(input) if input else None
        self.requests.append(Request(method, endpoint, body))
        status, result = self.respond(method, endpoint.split("?")[0], body)
        if self.lose_creation_response and endpoint == "user/repos" and status == 201:
            self.lose_creation_response = False
            raise subprocess.TimeoutExpired(arguments, timeout)
        message = result.get("message", "synthetic-private-value")
        error = f"gh: HTTP {status}" if method == "HEAD" else f"gh: {message} (HTTP {status})"
        return subprocess.CompletedProcess(
            arguments,
            0 if status < 400 else 1,
            b"" if method == "HEAD" else json.dumps(result).encode(),
            b"" if status < 400 else error.encode(),
        )

    def respond(self, method: str, endpoint: str, body: dict | None) -> tuple[int, dict]:
        if not self.authentication:
            return 401, {"message": "synthetic-private-value"}
        if endpoint == "user":
            return 200, {"login": "student"}
        if method == "POST" and (endpoint == "user/repos" or endpoint.startswith("orgs/")):
            owner = "student" if endpoint == "user/repos" else endpoint.split("/")[1]
            return 201, self.create(f"{owner}/{body['name']}")
        parts = endpoint.split("/")
        name = "/".join(parts[1:3])
        remote = self.repositories.get(name)
        if remote is None:
            return 404, {}
        action = "/".join(parts[3:])
        if not action and method == "PATCH":
            remote["private"] = body["visibility"] == "private"
            return 200, remote
        if not action:
            return 200, remote
        if action.startswith("git/ref/heads/"):
            return 200, {"object": {"sha": remote["head"]}}
        if action.startswith("git/commits/"):
            return 200, self.commits[parts[-1]]
        if action.startswith("git/trees/"):
            sha = parts[-1]
            return 200, {
                "sha": sha,
                "truncated": False,
                "tree": [
                    {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha(content)}
                    for path, content in self.trees[sha].items()
                ],
            }
        if action.startswith("git/blobs/") and method == "HEAD":
            return (200, {}) if self.known(parts[-1]) is not None else (404, {})
        if action.startswith("git/blobs/"):
            content = next(
                value
                for tree in self.trees.values()
                for value in tree.values()
                if blob_sha(value) == parts[-1]
            )
            return 200, {"content": base64.b64encode(content).decode(), "encoding": "base64"}
        if action == "git/blobs" and method == "POST":
            if self.upload_limit is not None:
                if self.upload_limit == 0:
                    raise subprocess.TimeoutExpired(["gh"], 45)
                self.upload_limit -= 1
            content = base64.b64decode(body["content"])
            sha = blob_sha(content)
            self.blobs[sha] = content
            return 201, {"sha": sha}
        if action == "git/trees" and method == "POST":
            files = dict(self.trees[body["base_tree"]])
            for entry in body["tree"]:
                if "sha" in entry and entry["sha"] is None:
                    files.pop(entry["path"], None)
                else:
                    files[entry["path"]] = (
                        entry["content"].encode()
                        if "content" in entry
                        else self.known(entry["sha"])
                    )
            return 201, {"sha": self.tree(files)}
        if action == "git/commits" and method == "POST":
            return 201, {"sha": self.commit(body["tree"], body["parents"])}
        if action.startswith("git/refs/heads/") and method == "PATCH":
            assert body["force"] is False
            if self.concurrent_push:
                self.edit(name, "README.md", b"Concurrent remote edit")
            if self.commits[body["sha"]]["parents"] != [remote["head"]]:
                return 422, {}
            remote["head"] = body["sha"]
            return 200, {"object": {"sha": remote["head"]}}
        if action == "pages":
            if method == "POST":
                if not self.plan_eligible and remote["private"]:
                    return 422, {
                        "message": "Your current plan does not support GitHub Pages for "
                        "this repository."
                    }
                self.pages[name] = {
                    "html_url": f"https://student.github.io/{parts[2]}/",
                    "source": body["source"],
                    "public": True,
                    "build_type": "legacy",
                }
                return 201, self.pages[name]
            return (200, self.pages[name]) if name in self.pages else (404, {})
        if action == "pages/builds/latest":
            return 200, {"status": self.build_status, "commit": self.build_commit or remote["head"]}
        if action.endswith("/check-runs"):
            return 200, {
                "total_count": 1,
                "check_runs": [
                    {
                        "status": self.check_status,
                        "conclusion": self.check_conclusion
                        if self.check_status == "completed"
                        else None,
                    }
                ],
            }
        if action == "actions/runs":
            return 200, {
                "total_count": 1,
                "workflow_runs": [
                    {
                        "status": self.workflow_status,
                        "conclusion": "success" if self.workflow_status == "completed" else None,
                    }
                ],
            }
        if action.endswith("/status"):
            return 200, {"state": "pending", "total_count": 0}
        raise AssertionError(f"Unexpected synthetic request: {method} {endpoint}")
