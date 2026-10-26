"""Allowlisted static exports and optimistic, site-only GitHub commits."""

import base64
import binascii
import hashlib
import json
from pathlib import Path
from typing import Final, Literal
from urllib.parse import quote

from pydantic import Field, ValidationError

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.study_build import TEMPLATE_FILES, _inline_math
from tum_mcp.study_github import Commit, GitHub, GitObject, Head, Response, Tree
from tum_mcp.study_models import Digest
from tum_mcp.study_publish_models import GitSha, Publication
from tum_mcp.study_store import digest

MARKER: Final = "tum-mcp-site.json"
SITE_FILES: Final = (*TEMPLATE_FILES, "data.mjs", ".nojekyll")


class SiteMarker(Frozen):
    schema_version: Literal[1] = 1
    course_identity: Digest
    files: dict[str, GitSha] = Field(max_length=100)


class Blob(Response):
    content: str
    encoding: str


def blob_sha(content: bytes) -> str:
    """Git object identifiers are SHA-1 by protocol, not a security digest."""
    return hashlib.sha1(
        f"blob {len(content)}\0".encode() + content, usedforsecurity=False
    ).hexdigest()


def export_site(root: Path, *, include_exercises: bool = False) -> dict[str, bytes]:
    """Export only the renderer, never materials, comments, state, audio or arbitrary files."""
    output = {name: app_path(root, name).read_bytes() for name in (*TEMPLATE_FILES, "data.mjs")}
    data = output["data.mjs"]
    if not data.startswith(b"export default "):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Rebuild generated study data before publishing."
        )
    if not include_exercises:
        try:
            payload = json.loads(data.removeprefix(b"export default ").removesuffix(b";\n"))
        except ValueError:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Rebuild the generated site data.") from None
        if "exercises" in payload:
            if not payload.get("units"):
                raise CampusError(
                    Code.ACTION_REQUIRED, "Explicitly include Exercises to publish it."
                )
            payload.pop("exercises")
            payload["workspaces"] = ["study"]
            references = {s["key"] for unit in payload["units"] for s in unit["sources"]}
            payload["sources"] = {k: v for k, v in payload["sources"].items() if k in references}
            payload["inlineMath"] = _inline_math([payload["introduction"], payload["units"]])
            data = b"export default " + json.dumps(payload, ensure_ascii=True).encode() + b";\n"
    output["data.mjs"] = (
        data.replace(b"export default ", b"const data = ", 1)
        + b"data.hosted = true;\nexport default data;\n"
    )
    output["index.html"] = output["index.html"].replace(
        b"A private local course notebook", b"A source-backed course notebook"
    )
    output[".nojekyll"] = b""
    if sum(len(value) for value in output.values()) > 16 * 1024 * 1024:
        raise CampusError(Code.ACTION_REQUIRED, "The static study export exceeds 16 MiB.")
    return output


def site_digest(site: dict[str, bytes]) -> str:
    return digest(
        json.dumps({name: digest(value) for name, value in site.items()}, sort_keys=True).encode()
    )


def remote_tree(github: GitHub, publication: Publication) -> tuple[str, Tree]:
    base = f"repos/{publication.repository}"
    head = github.require(f"{base}/git/ref/heads/{quote(publication.branch, safe='')}", Head)
    commit = github.require(f"{base}/git/commits/{head.object.sha}", Commit)
    tree = github.require(f"{base}/git/trees/{commit.tree.sha}?recursive=1", Tree)
    if tree.truncated:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "The remote tree is too large to inspect safely."
        )
    return head.object.sha, tree


def verify_marker(github: GitHub, publication: Publication, tree: Tree) -> None:
    marker = next((item for item in tree.tree if item.path == MARKER), None)
    if marker is None:
        if tree.tree and {item.path for item in tree.tree} != {"README.md"}:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "The repository is not a managed study site."
            )
        if publication.site_digest is not None:
            raise CampusError(Code.WORKSPACE_CONFLICT, "The remote study marker was removed.")
        return
    blob = github.require(f"repos/{publication.repository}/git/blobs/{marker.sha}", Blob)
    if blob.encoding != "base64":
        raise CampusError(Code.INVALID_RESPONSE, "Unexpected remote study marker encoding.")
    try:
        value = SiteMarker.model_validate_json(base64.b64decode(blob.content))
    except (ValueError, binascii.Error, ValidationError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "The remote study marker needs review."
        ) from None
    if value.course_identity != publication.course_identity or not set(value.files) <= set(
        SITE_FILES
    ):
        raise CampusError(
            Code.SCOPE_DENIED, "The remote repository is bound to another study site."
        )
    actual = {
        item.path: item.sha for item in tree.tree if item.type == "blob" and item.mode == "100644"
    }
    if set(SITE_FILES).intersection(actual).difference(value.files):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Unmanaged remote website files need review.")
    if any(actual.get(name) != sha for name, sha in value.files.items()):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Remote study files were edited; review before publishing."
        )


def commit_site(github: GitHub, publication: Publication, site: dict[str, bytes]) -> str:
    """Preserve unrelated remote files and reject concurrent branch advancement."""
    head, tree = remote_tree(github, publication)
    verify_marker(github, publication, tree)
    marker = SiteMarker(
        course_identity=publication.course_identity,
        files={name: blob_sha(value) for name, value in site.items()},
    )
    desired = {**site, MARKER: marker.model_dump_json(indent=2).encode()}
    actual = {
        item.path: item.sha for item in tree.tree if item.type == "blob" and item.mode == "100644"
    }
    changed = {
        name: value for name, value in desired.items() if actual.get(name) != blob_sha(value)
    }
    if not changed:
        return head
    base = f"repos/{publication.repository}"
    entries: list[dict[str, str]] = []
    for name, value in changed.items():
        entry = {"path": name, "mode": "100644", "type": "blob"}
        try:
            entry["content"] = value.decode("utf-8")
        except UnicodeDecodeError:
            blob = github.require(
                f"{base}/git/blobs",
                GitObject,
                method="POST",
                payload={"encoding": "base64", "content": base64.b64encode(value).decode("ascii")},
            )
            entry["sha"] = blob.sha
        entries.append(entry)
    new_tree = github.require(
        f"{base}/git/trees",
        GitObject,
        method="POST",
        payload={
            "base_tree": tree.sha,
            "tree": entries,
        },
    )
    commit = github.require(
        f"{base}/git/commits",
        GitObject,
        method="POST",
        payload={
            "message": "Update study website",
            "tree": new_tree.sha,
            "parents": [head],
        },
    )
    github.require(
        f"{base}/git/refs/heads/{quote(publication.branch, safe='')}",
        Head,
        method="PATCH",
        payload={"sha": commit.sha, "force": False},
    )
    return commit.sha
