"""Private browser receipts bound to the exact app, browser and executed states."""

import io
import json
import platform
from collections.abc import Iterable
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Literal

from filelock import FileLock
from PIL import Image
from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.content.figures import figure_images
from tum_mcp.course.project.models import Digest
from tum_mcp.course.project.store import Write, apply, confined, digest, private_path, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import BrowserChoice, discover_browsers
from tum_mcp.settings import Frozen


class BrowserBuild(Frozen):
    build: Digest
    # The renderer: templates and images, everything built except the content data.
    shell: Digest
    checks: Digest
    browser: Digest
    managed: bool


class Earlier(Frozen):
    """A passing check from an earlier build of the same renderer, kept until rechecked."""

    revision: str
    captures: tuple[str, ...] = ()
    digests: tuple[Digest, ...] = ()


class BrowserReceipt(Frozen):
    schema_version: Literal[1] = 1
    identity: BrowserBuild
    states: dict[str, bool] = Field(default_factory=dict)
    captures: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    capture_digests: dict[str, tuple[Digest, ...]] = Field(default_factory=dict)
    # Passing command results can be replayed for exactly the same request.
    results: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    # The revision of the item each check covered, so a rebuild keeps unchanged items' checks.
    revisions: dict[str, str] = Field(default_factory=dict)
    earlier: dict[str, Earlier] = Field(default_factory=dict)

    def pending(self) -> dict[str, Earlier]:
        """Earlier passes this build has not rechecked yet."""
        return {key: value for key, value in self.earlier.items() if key not in self.states}

    def carried(self, root: Path) -> dict[str, Earlier]:
        """This build's passing checks, offered to the next build of the same renderer."""
        passed = {
            key: self.checked(key)
            for key in self.states
            if key in self.revisions and self.evidence(root, key)
        }
        return self.pending() | passed

    def evidence(self, root: Path, key: str) -> bool:
        return self.states.get(key) is True and captured(
            root, key, self.captures.get(key, ()), self.capture_digests.get(key, ())
        )

    def checked(self, key: str) -> Earlier:
        return Earlier(
            revision=self.revisions[key],
            captures=self.captures.get(key, ()),
            digests=self.capture_digests.get(key, ()),
        )


def pictured(key: str) -> bool:
    return key.startswith(("visual/phone/", "visual/desktop/"))


def _capture_bytes(root: Path, path: str) -> bytes | None:
    if not path.startswith(".tum-mcp/visuals/"):
        return None
    try:
        return read_bytes(confined(root, path))
    except (CampusError, OSError):
        return None


def captured(root: Path, key: str, captures: tuple[str, ...], digests: tuple[Digest, ...]) -> bool:
    """A photographed check counts only with its exact original sheets."""
    return not pictured(key) or (
        bool(captures)
        and len(captures) == len(digests)
        and all(
            (data := _capture_bytes(root, path)) and digest(data) == expected
            for path, expected in zip(captures, digests, strict=True)
        )
    )


def _capture_digests(root: Path, paths: tuple[str, ...]) -> tuple[Digest, ...]:
    hashes: list[Digest] = []
    for path in paths:
        data = _capture_bytes(root, path)
        if not data:
            break
        try:
            with Image.open(io.BytesIO(data), formats=("PNG",)) as image:
                image.verify()
            with Image.open(io.BytesIO(data), formats=("PNG",)) as image:
                _ = image.load()
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
            break
        hashes.append(digest(data))
    return tuple(hashes) if len(hashes) == len(paths) else ()


def build_files(root: Path) -> tuple[Digest, bool]:
    hashes, managed = _built(root)
    return digest(json.dumps(hashes, sort_keys=True).encode()), managed


def _built(root: Path) -> tuple[dict[str, str], bool]:
    from tum_mcp.course.app.build import TEMPLATE_FILES

    data = read_bytes(confined(root, "app/data.mjs"))
    if data is None:
        raise CampusError(Code.ACTION_REQUIRED, "Build the study site first.")
    try:
        payload = json.loads(data.decode().removeprefix("export default ").removesuffix(";\n"))
    except (UnicodeError, json.JSONDecodeError):
        raise CampusError(
            Code.INVALID_RESPONSE, "The built app data is invalid. Rebuild it."
        ) from None
    bundled = files("tum_mcp.bundled").joinpath("course_app/site")
    hashes: dict[str, str] = {"data.mjs": digest(data)}
    managed = True
    for name in TEMPLATE_FILES:
        actual = read_bytes(confined(root, f"app/{name}"))
        if actual is None:
            raise CampusError(Code.ACTION_REQUIRED, f"The built app lacks {name}. Rebuild it.")
        managed &= actual == bundled.joinpath(name).read_bytes()
        hashes[name] = digest(actual)
    assets = set(figure_images(payload))
    thumbnails = confined(root, "app/lecture-assets")
    if thumbnails.is_dir():
        assets.update(f"lecture-assets/{path.name}" for path in thumbnails.iterdir())
    for name in sorted(assets):
        actual = read_bytes(confined(root, f"app/{name}"))
        if actual is None:
            raise CampusError(Code.ACTION_REQUIRED, f"The built app lacks {name}.")
        hashes[name] = digest(actual)
    return hashes, managed


def browser_choice() -> BrowserChoice:
    choices = discover_browsers()
    if not choices:
        raise CampusError(Code.ACTION_REQUIRED, "Install Chrome, Edge or Chromium for the check.")
    return choices[0]


def browser_identity(root: Path, browser: BrowserChoice) -> BrowserBuild:
    hashes, managed = _built(root)
    build = digest(json.dumps(hashes, sort_keys=True).encode())
    shell = digest(
        json.dumps({k: v for k, v in hashes.items() if k != "data.mjs"}, sort_keys=True).encode()
    )
    executable = Path(browser.executable).resolve()
    stat = executable.stat()
    bundled = files("tum_mcp.bundled")
    scripts = ("interaction_check.js", "visual_check.js", "visual_inject.js")
    checks = digest(
        Path(__file__).read_bytes()
        + Path(__file__).with_name("visuals.py").read_bytes()
        + b"".join(bundled.joinpath(name).read_bytes() for name in scripts)
    )
    host = [
        platform.system(),
        platform.machine(),
        version("playwright"),
        str(executable),
        stat.st_size,
        stat.st_mtime_ns,
    ]
    return BrowserBuild(
        build=build,
        shell=shell,
        checks=checks,
        browser=digest(json.dumps(host).encode()),
        managed=managed,
    )


def read_receipt(root: Path) -> BrowserReceipt | None:
    body = read_bytes(private_path(root, "browser-check.json"))
    if body is not None:
        try:
            return BrowserReceipt.model_validate_json(body)
        except ValidationError:
            return None
    return None


def current_sheets(root: Path) -> dict[str, dict[str, list[str]]]:
    """Link captured sheets only when the rendered build still matches the draft."""
    from tum_mcp.course.app.build import current_data

    receipt = read_receipt(root)
    if receipt is None or not receipt.captures:
        return {}
    try:
        if read_bytes(confined(root, "app/data.mjs")) != current_data(root):
            return {}
        if build_files(root) != (receipt.identity.build, receipt.identity.managed):
            return {}
    except CampusError:
        return {}

    sheets: dict[str, dict[str, list[str]]] = {}
    for key, paths in receipt.captures.items():
        if pictured(key) and receipt.evidence(root, key):
            _, width, item = key.split("/", 2)
            sheets.setdefault(item, {})[width] = list(paths)
    return sheets


def save_receipt(
    root: Path,
    identity: BrowserBuild,
    states: dict[str, bool],
    result: tuple[str, dict[str, JsonValue]] | None = None,
    *,
    captures: dict[str, tuple[str, ...]] | None = None,
    retained: dict[str, Earlier] | None = None,
    revisions: dict[str, str] | None = None,
) -> None:
    path = private_path(root, "browser-check.json")
    with FileLock(str(private_path(root, "update.lock"))):
        if build_files(root) != (identity.build, identity.managed):
            raise CampusError(Code.STALE_RESULT, "The built app changed during browser checks.")
        previous = read_receipt(root)
        if previous and previous.identity == identity:
            current = previous
        elif previous and _rebuilt(previous.identity, identity):
            current = BrowserReceipt(identity=identity, earlier=previous.carried(root))
        else:
            current = BrowserReceipt(identity=identity)
        paths = captures or {}
        kept = retained or {}
        hashes = {key: _capture_digests(root, value) for key, value in paths.items()}
        hashes.update({key: entry.digests for key, entry in kept.items() if entry.digests})
        paths = paths | {key: entry.captures for key, entry in kept.items() if entry.captures}
        for key, passed in states.items():
            if (
                passed
                and pictured(key)
                and (
                    not hashes.get(key)
                    or (key in kept and not captured(root, key, paths[key], hashes[key]))
                )
            ):
                raise CampusError(Code.STALE_RESULT, f"{key}: missing or invalid contact sheets.")
        results = dict(current.results) if all(states.values()) else {}
        if result and result[1].get("passed") is True:
            results[result[0]] = result[1]
        updated = current.model_copy(
            update={
                "states": current.states | states,
                "results": results,
                "captures": {
                    key: paths for key, paths in current.captures.items() if key not in states
                }
                | paths,
                "capture_digests": {
                    key: value
                    for key, value in current.capture_digests.items()
                    if key not in states
                }
                | hashes,
                "revisions": current.revisions | (revisions or {}),
            }
        )
        apply(
            root,
            (
                Write(
                    ".tum-mcp/browser-check.json",
                    read_bytes(path),
                    updated.model_dump_json(indent=2).encode(),
                ),
            ),
        )


def result_key(kind: str, targets: Iterable[str], widths: Iterable[str]) -> str:
    return digest(json.dumps([kind, sorted(targets), list(widths)]).encode())


def reusable(root: Path, identity: BrowserBuild, revisions: dict[str, str]) -> dict[str, Earlier]:
    """Find passing checks for the same item revision, with stock-only cross-build reuse."""
    receipt = read_receipt(root)
    if receipt is None:
        return {}
    if receipt.identity == identity:
        pool = receipt.pending() | {
            key: receipt.checked(key)
            for key in revisions
            if key in receipt.revisions and receipt.states.get(key) is True
        }
    elif _rebuilt(receipt.identity, identity):
        pool = receipt.carried(root)
    else:
        return {}
    return {
        key: pool[key]
        for key, revision in revisions.items()
        if key in pool
        and pool[key].revision == revision
        and captured(root, key, pool[key].captures, pool[key].digests)
    }


def _rebuilt(before: BrowserBuild, after: BrowserBuild) -> bool:
    """Only the content data changed: same templates, images, checks and browser."""
    return before.managed and before.model_copy(update={"build": after.build}) == after


def cached(
    root: Path, identity: BrowserBuild, request: str, states: Iterable[str]
) -> dict[str, JsonValue] | None:
    receipt = read_receipt(root)
    if receipt and receipt.identity == identity:
        result = receipt.results.get(request)
        if (
            result
            and result.get("passed") is True
            and all(receipt.evidence(root, key) for key in states)
        ):
            return result
    return None
