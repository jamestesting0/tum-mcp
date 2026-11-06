"""Short command output for agents; the full result is saved for a targeted read."""

import json
from pathlib import Path

import typer
from pydantic import JsonValue

from tum_mcp.course.project.store import PRIVATE, confined


def summarize(value: JsonValue, depth: int = 0) -> JsonValue:
    """Scalars stay, long text is cut, lists become a count and their first entries."""
    match value:
        case list():
            if depth >= 2 or not value:
                return {"count": len(value)}
            return {
                "count": len(value),
                "first": [summarize(item, depth + 1) for item in value[:3]],
            }
        case dict():
            if depth >= 3:
                return {"keys": len(value)}
            return {key: summarize(item, depth + 1) for key, item in value.items()}
        case str() if len(value) > 160:
            return value[:157] + "..."
        case _:
            return value


def emit(root: Path, command: str, result: JsonValue, *, full: bool) -> None:
    name = f"{PRIVATE}/out/{command}.json"
    path = confined(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    if full:
        typer.echo(text)
        return
    summary = {"summary": summarize(result), "full": name}
    typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))
