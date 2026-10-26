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
from tum_mcp.lecture_assets import ASSET
from tum_mcp.settings import Frozen
from tum_mcp.study_build import TEMPLATE_FILES
from tum_mcp.study_github import Commit, GitHub, GitObject, Head, Response, Tree
from tum_mcp.study_models import Digest, is_studocu_link
from tum_mcp.study_publish_models import GitSha, Publication, course_identity
from tum_mcp.study_publish_projection import assets, project
from tum_mcp.study_store import digest, load_state

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


def preflight(site: dict[str, bytes], identity: str) -> SiteMarker:
    if len(site) + 1 > 100:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "The static export exceeds 100 managed files including its marker.",
        )
    if any(name not in SITE_FILES and ASSET.fullmatch(name) is None for name in site):
        raise CampusError(Code.SCOPE_DENIED, "The export contains an unmanaged site path.")
    marker = SiteMarker(
        course_identity=identity, files={name: blob_sha(value) for name, value in site.items()}
    )
    if (
        sum(len(value) for value in site.values()) + len(marker.model_dump_json(indent=2).encode())
        > 16 * 1024**2
    ):
        raise CampusError(
            Code.ACTION_REQUIRED, "The static study export exceeds 16 MiB including its marker."
        )
    return marker


def export_site(
    root: Path, *, include_exercises: bool = False, include_lectures: bool = False
) -> dict[str, bytes]:
    """Export referenced public workspaces; private evidence and arbitrary files stay local."""
    output = {name: app_path(root, name).read_bytes() for name in (*TEMPLATE_FILES, "data.mjs")}
    data = output["data.mjs"]
    checked = _check_supplementary_sources(
        root, data, include_exercises=include_exercises, include_lectures=include_lectures
    )
    payload = (
        checked
        if checked is not None
        else project(data, include_exercises=include_exercises, include_lectures=include_lectures)
    )
    original = json.loads(data.removeprefix(b"export default ").removesuffix(b";\n"))
    if payload != original:
        data = b"export default " + json.dumps(payload, ensure_ascii=True).encode() + b";\n"
    output["data.mjs"] = (
        data.replace(b"export default ", b"const data = ", 1)
        + b"data.hosted = true;\nexport default data;\n"
    )
    output.update(assets(root, payload))
    output["index.html"] = output["index.html"].replace(
        b"A private local course notebook", b"A source-backed course notebook"
    )
    output[".nojekyll"] = b""
    preflight(output, course_identity(load_state(root).course))
    return output


def _check_supplementary_sources(
    root: Path, data: bytes, *, include_exercises: bool, include_lectures: bool
) -> dict | None:
    """Refuse exports that reference personal student uploads, from live source bindings."""
    state = load_state(root)
    private_bindings = {item.key for item in state.course.bindings if item.provider == "studocu"}
    private_keys = {
        item.resource.key
        for item in state.resources
        if item.resource.binding in private_bindings or is_studocu_link(item.resource.url)
    }
    if not private_bindings and not private_keys:
        return None
    from tum_mcp.exercise_data import read_exercises, stale_exercises
    from tum_mcp.lecture_data import read_lectures, stale_lectures
    from tum_mcp.study_build import _app_data, read_content, stale_units

    try:
        generated = json.loads(data.removeprefix(b"export default ").removesuffix(b";\n"))
    except ValueError:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Rebuild the generated site data.") from None
    if not isinstance(generated, dict) or not isinstance(generated.get("sources"), dict):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Rebuild the generated site data.")
    content = read_content(root) if app_path(root, "content.json").exists() else None
    exercises = read_exercises(root) if include_exercises else None
    lectures = read_lectures(root) if include_lectures else None
    if (
        (content and stale_units(root, state, content))
        or (exercises and stale_exercises(root, state, exercises))
        or (lectures and stale_lectures(root, state, lectures))
    ):
        raise CampusError(Code.STALE_RESULT, "Rebuild after refreshing changed source material.")
    expected = _app_data(state, content, exercises, lectures, root)
    excluded = (not include_exercises and "exercises" in generated) or (
        not include_lectures and "lectures" in generated
    )
    if not excluded and generated.get("inlineMath") != expected.get("inlineMath"):
        raise CampusError(Code.STALE_RESULT, "Rebuild generated study data before publication.")
    keys = {s.key for unit in content.units for s in unit.sources} if content else set()
    if exercises:
        keys.update(s.key for group in exercises.sets for ex in group.exercises for s in ex.sources)
    if lectures:
        keys.update(s.key for lecture in lectures.lectures for s in lecture.sources)
    projection = project(
        data, include_exercises=include_exercises, include_lectures=include_lectures
    )
    expected_data = b"export default " + json.dumps(expected, ensure_ascii=True).encode() + b";\n"
    expected_projection = project(
        expected_data, include_exercises=include_exercises, include_lectures=include_lectures
    )
    derived = {"generation", "incompleteSources"}
    matches = {key: value for key, value in projection.items() if key not in derived} == {
        key: value for key, value in expected_projection.items() if key not in derived
    }
    if not matches:
        raise CampusError(Code.STALE_RESULT, "Rebuild generated study data before publication.")
    resources = {item.resource.key: item for item in state.resources}
    missing = keys - resources.keys()
    protected = sorted(key for key in keys if key in private_keys)
    if missing or protected:
        raise CampusError(
            Code.SCOPE_DENIED,
            "Publication includes unavailable or personal-use sources: "
            + ", ".join(sorted(missing) + protected),
        )
    return expected_projection


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
        name not in SITE_FILES and ASSET.fullmatch(name) is None for name in value.files
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


def commit_site(github: GitHub, publication: Publication, site: dict[str, bytes]) -> str:
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
