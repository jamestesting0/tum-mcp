"""Readiness problems of the items changed since the previous build, shown while writing."""

import json
from pathlib import Path

from tum_mcp.course.project.store import private_path, read_bytes
from tum_mcp.course.review.items import digest

INDEX = "out/changed-items.json"


def changed_problems(root: Path) -> dict[str, list[str]]:
    """Invariant problems of the items whose content changed since the last call."""
    from tum_mcp.course.review import loop
    from tum_mcp.course.review.models import COURSE_WIDE_FLAGS, INVARIANT_FLAGS

    context = loop.load(root)
    path = private_path(root, INDEX)
    body = read_bytes(path)
    before: dict[str, str] = json.loads(body) if body else {}
    now = {key: digest(item.value) for key, item in context.items.items() if key != "course"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(now, indent=2, sort_keys=True), encoding="utf-8")
    problems: dict[str, list[str]] = {}
    for key, value in now.items():
        if before.get(key) == value:
            continue
        found = [
            f"{flag['flag']}: {flag['detail']}"
            for flag in context.flags_by_item.get(key, [])
            if flag["flag"] in INVARIANT_FLAGS and flag["flag"] not in COURSE_WIDE_FLAGS
        ]
        if found:
            problems[key] = [
                f"{line} ({found.count(line)} places)" if found.count(line) > 1 else line
                for line in dict.fromkeys(found)
            ]
    return problems
