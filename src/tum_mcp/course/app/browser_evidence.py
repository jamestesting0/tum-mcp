"""Private browser receipts bound to the exact app, browser and executed states."""

import json
import platform
from collections.abc import Iterable
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Literal

from filelock import FileLock
from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.content.figures import figure_images
from tum_mcp.course.project.models import Digest
from tum_mcp.course.project.store import Write, apply, confined, digest, private_path, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import BrowserChoice, discover_browsers
from tum_mcp.settings import Frozen


class BrowserBuild(Frozen):
    build: Digest
    checks: Digest
    browser: Digest
    managed: bool


class BrowserReceipt(Frozen):
    schema_version: Literal[1] = 1
    identity: BrowserBuild
    states: dict[str, bool] = Field(default_factory=dict)
    captures: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # Passing command results can be replayed for exactly the same request.
    results: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)

    def evidence(self, root: Path, key: str) -> bool:
        if self.states.get(key) is not True:
            return False
        if not key.startswith(("visual/phone/", "visual/desktop/")):
            return True
        captures = self.captures.get(key, ())
        try:
            return bool(captures) and all(
                path.startswith(".tum-mcp/visuals/") and confined(root, path).is_file()
                for path in captures
            )
        except CampusError:
            return False


def build_files(root: Path) -> tuple[Digest, bool]:
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
    return digest(json.dumps(hashes, sort_keys=True).encode()), managed


def browser_choice() -> BrowserChoice:
    choices = discover_browsers()
    if not choices:
        raise CampusError(Code.ACTION_REQUIRED, "Install Chrome, Edge or Chromium for the check.")
    return choices[0]


def browser_identity(root: Path, browser: BrowserChoice) -> BrowserBuild:
    build, managed = build_files(root)
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
        platform.platform(),
        version("playwright"),
        str(executable),
        stat.st_size,
        stat.st_mtime_ns,
    ]
    return BrowserBuild(
        build=build,
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


def current_sheets(root: Path) -> dict[str, dict[str, JsonValue]]:
    """Link captured sheets only when the rendered build still matches the draft."""
    from tum_mcp.course.app.build import current_data

    receipt = read_receipt(root)
    if receipt is None or not receipt.identity.managed or not receipt.captures:
        return {}
    try:
        if read_bytes(confined(root, "app/data.mjs")) != current_data(root):
            return {}
        if build_files(root) != (receipt.identity.build, True):
            return {}
    except CampusError:
        return {}

    sheets: dict[str, dict[str, JsonValue]] = {}
    for key, paths in receipt.captures.items():
        if key.startswith(("visual/phone/", "visual/desktop/")) and receipt.evidence(root, key):
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
) -> None:
    path = private_path(root, "browser-check.json")
    with FileLock(str(private_path(root, "update.lock"))):
        if build_files(root) != (identity.build, identity.managed):
            raise CampusError(Code.STALE_RESULT, "The built app changed during browser checks.")
        previous = read_receipt(root)
        current = (
            previous
            if previous and previous.identity == identity
            else BrowserReceipt(identity=identity)
        )
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
                | (captures or {}),
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


def cached(
    root: Path, identity: BrowserBuild, request: str, states: Iterable[str]
) -> dict[str, JsonValue] | None:
    receipt = read_receipt(root)
    if identity.managed and receipt and receipt.identity == identity:
        result = receipt.results.get(request)
        if (
            result
            and result.get("passed") is True
            and all(receipt.evidence(root, key) for key in states)
        ):
            return result
    return None
