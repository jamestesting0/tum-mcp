"""Allowlisted static exports and optimistic, site-only GitHub commits."""

import base64
import binascii
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal
from urllib.parse import quote

from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.app.build import RETIRED_TEMPLATE_FILES, TEMPLATE_FILES
from tum_mcp.course.app.github import Commit, GitHub, GitObject, Head, Response, Tree
from tum_mcp.course.app.publish_media import EMPTY, MEDIA, media_files
from tum_mcp.course.app.publish_models import GitSha, Publication, course_identity
from tum_mcp.course.app.publish_projection import assets, project
from tum_mcp.course.content.figures import FIGURE_IMAGE
from tum_mcp.course.content.store import present
from tum_mcp.course.lecture.assets import ASSET
from tum_mcp.course.project.models import Digest
from tum_mcp.course.project.paths import app_path
from tum_mcp.course.project.store import digest, load_state
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

MARKER: Final = "tum-mcp-site.json"
# Every export carries both media indexes, empty when nothing is installed.
SITE_FILES: Final = (*TEMPLATE_FILES, "data.mjs", ".nojekyll", *EMPTY)
# Markers from older exports may list retired files; the next commit removes them.
KNOWN_SITE_FILES: Final = frozenset((*SITE_FILES, *RETIRED_TEMPLATE_FILES))
MiB: Final = 1024**2
APP_BUDGET: Final = 16 * MiB
# GitHub serves Pages sites up to 1 GB and warns about files above 50 MB.
SITE_BUDGET: Final = 900 * MiB
FILE_BUDGET: Final = 40 * MiB
MAX_FILES: Final = 1000
# New uploads start only this long into a call, so agent command limits never cut one off.
UPLOAD_SECONDS: Final = 60


def _asset_path(name: str) -> bool:
    return (
        ASSET.fullmatch(name) is not None
        or FIGURE_IMAGE.fullmatch(name) is not None
        or MEDIA.fullmatch(name) is not None
    )


class SiteMarker(Frozen):
    schema_version: Literal[1] = 1
    course_identity: Digest
    files: dict[str, GitSha] = Field(max_length=MAX_FILES)


@dataclass(frozen=True, slots=True)
class Uploading:
    sent: int
    total: int


class Blob(Response):
    content: str
    encoding: str


def blob_sha(content: bytes) -> str:
    """Git object identifiers are SHA-1 by protocol, not a security digest."""
    return hashlib.sha1(
        f"blob {len(content)}\0".encode() + content, usedforsecurity=False
    ).hexdigest()


def _sizes(site: dict[str, bytes], names: list[str]) -> str:
    largest = sorted(names, key=lambda name: len(site[name]), reverse=True)[:3]
    return ", ".join(f"{name} ({len(site[name]) / MiB:.1f} MiB)" for name in largest)


def preflight(site: dict[str, bytes], identity: str) -> SiteMarker:
    if len(site) + 1 > MAX_FILES:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"The static export exceeds {MAX_FILES} managed files including its marker.",
        )
    if any(name not in SITE_FILES and not _asset_path(name) for name in site):
        raise CampusError(Code.SCOPE_DENIED, "The export contains an unmanaged site path.")
    marker = SiteMarker(
        course_identity=identity, files={name: blob_sha(value) for name, value in site.items()}
    )
    media = [name for name in site if MEDIA.fullmatch(name)]
    app = sum(len(value) for name, value in site.items() if name not in media)
    if app + len(marker.model_dump_json(indent=2).encode()) > APP_BUDGET:
        raise CampusError(
            Code.ACTION_REQUIRED, "The static study export exceeds 16 MiB including its marker."
        )
    if large := [name for name in media if len(site[name]) > FILE_BUDGET]:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Media files above 40 MiB cannot be published: {_sizes(site, large)}.",
        )
    if sum(len(value) for value in site.values()) > SITE_BUDGET:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"The site with its videos and audio exceeds 900 MiB. Largest: {_sizes(site, media)}.",
        )
    return marker


def export_site(root: Path, *, media: bool = True) -> dict[str, bytes]:
    """Export every prepared workspace without originals, provenance or personal state."""
    output = {name: app_path(root, name).read_bytes() for name in (*TEMPLATE_FILES, "data.mjs")}
    data = output["data.mjs"]
    payload = _checked_payload(root, data)
    output.update(assets(root, payload))
    output["data.mjs"] = (
        b"const data = "
        + json.dumps(project(payload), ensure_ascii=True, separators=(",", ":")).encode()
        + b";\ndata.hosted = true;\nexport default data;\n"
    )
    output[".nojekyll"] = b""
    output.update(media_files(root) if media else EMPTY)
    preflight(output, course_identity(load_state(root).course))
    return output


def _checked_payload(root: Path, data: bytes) -> dict[str, JsonValue]:
    """Check the complete local payload before removing any source relationships."""
    state = load_state(root)
    from tum_mcp.course.app.build import _app_data, read_content, stale_units
    from tum_mcp.course.content.exam_data import read_exam, stale_exam
    from tum_mcp.course.content.exercise_data import read_exercises, stale_exercises
    from tum_mcp.course.lecture.data import read_lectures, stale_lectures

    if not data.startswith(b"export default "):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Rebuild the generated site data.")
    try:
        generated = json.loads(data.removeprefix(b"export default ").removesuffix(b";\n"))
    except ValueError:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Rebuild the generated site data.") from None
    content = read_content(root) if present(root, "study") else None
    exercises = read_exercises(root)
    lectures = read_lectures(root)
    exam = read_exam(root)
    if (
        (content and stale_units(root, state, content))
        or (exercises and stale_exercises(root, state, exercises))
        or (lectures and stale_lectures(root, state, lectures))
        or (exam and stale_exam(root, state, exam))
    ):
        raise CampusError(Code.STALE_RESULT, "Rebuild after refreshing changed source material.")
    expected = _app_data(state, content, exercises, lectures, root, exam)
    if generated != expected:
        raise CampusError(Code.STALE_RESULT, "Rebuild generated study data before publication.")
    return expected


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


def verify_marker(github: GitHub, publication: Publication, tree: Tree) -> SiteMarker | None:
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
    if value.course_identity != publication.course_identity or any(
        name not in KNOWN_SITE_FILES and not _asset_path(name) for name in value.files
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

    return value


def upload(github: GitHub, base: str, blobs: dict[str, bytes]) -> Uploading | None:
    """Send the blobs GitHub lacks; the remote is the progress record across bounded calls."""
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        present = dict(
            zip(
                blobs,
                pool.map(lambda sha: github.exists(f"{base}/git/blobs/{sha}"), blobs),
                strict=True,
            )
        )
    total = sum(len(value) for value in blobs.values())
    sent = sum(len(blobs[sha]) for sha, found in present.items() if found)
    uploaded = 0
    for sha, value in blobs.items():
        if present[sha]:
            continue
        # Every call sends at least one blob, so a slow connection still makes progress.
        if uploaded and time.monotonic() - started > UPLOAD_SECONDS:
            return Uploading(sent, total)
        uploaded += 1
        content = base64.b64encode(value).decode("ascii")
        _ = github.require(
            f"{base}/git/blobs",
            GitObject,
            method="POST",
            payload={"encoding": "base64", "content": content},
            # Allows about 0.5 Mbit/s of upload before the request counts as stalled.
            timeout=45 + 16 * len(content) // MiB,
        )
        sent += len(value)
    return None


def commit_site(
    github: GitHub, publication: Publication, site: dict[str, bytes]
) -> str | Uploading:
    """Preserve unrelated remote files and reject concurrent branch advancement."""
    marker = preflight(site, publication.course_identity)
    head, tree = remote_tree(github, publication)
    previous = verify_marker(github, publication, tree)
    desired = {**site, MARKER: marker.model_dump_json(indent=2).encode()}
    actual = {
        item.path: item.sha for item in tree.tree if item.type == "blob" and item.mode == "100644"
    }
    changed = {
        name: value for name, value in desired.items() if actual.get(name) != blob_sha(value)
    }
    if set(site).intersection(actual).difference(previous.files if previous else ()):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Unmanaged remote website files need review.")
    obsolete = set(previous.files).difference(site) if previous else set()
    if not changed and not obsolete:
        return head
    base = f"repos/{publication.repository}"
    entries: list[dict[str, str | None]] = [
        {"path": name, "mode": "100644", "type": "blob", "sha": None} for name in sorted(obsolete)
    ]
    binary: dict[str, bytes] = {}
    for name, value in changed.items():
        entry = {"path": name, "mode": "100644", "type": "blob"}
        try:
            entry["content"] = value.decode("utf-8")
        except UnicodeDecodeError:
            entry["sha"] = blob_sha(value)
            binary[entry["sha"]] = value
        entries.append(entry)
    if progress := upload(github, base, binary):
        return progress
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
