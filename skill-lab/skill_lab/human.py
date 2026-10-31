"""Human review: in-app passage comments and notes on a run, kept beside the judge's verdict."""

import json
from datetime import UTC, datetime
from pathlib import Path

from skill_lab import LabError, paths


def run_dir(round_id: str, run_id: str) -> Path:
    directory = paths.round_dir(round_id) / "runs" / run_id
    if not (directory / "run.json").is_file():
        raise LabError(f"No run {run_id} in round {round_id}.")
    return directory


def project_of(directory: Path) -> Path | None:
    record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    return directory / "workspace" / record["project"] if record.get("project") else None


def comments(directory: Path) -> list[dict]:
    project = project_of(directory)
    store = project / ".tum-mcp" / "comments.json" if project else None
    if store is None or not store.is_file():
        return []
    data = json.loads(store.read_text(encoding="utf-8"))
    found = []
    for item in data.get("comments", []):
        anchor = item.get("anchor") or {}
        found.append(
            {
                "status": item.get("status", "open"),
                "view": anchor.get("view"),
                "where": anchor.get("block_title"),
                "item": anchor.get("item_key") or anchor.get("exercise_key"),
                "quote": anchor.get("quote"),
                "note": item.get("text"),
            }
        )
    return found


def notes_path(round_id: str, run_id: str) -> Path:
    return paths.round_dir(round_id) / "human" / f"{run_id}.md"


def add_note(round_id: str, run_id: str, text: str) -> Path:
    run_dir(round_id, run_id)
    if not text.strip():
        raise LabError("The note is empty.")
    target = notes_path(round_id, run_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="minutes")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {stamp}\n\n{text.strip()}\n")
    return target


def export(round_id: str, run_id: str) -> dict:
    directory = run_dir(round_id, run_id)
    notes = notes_path(round_id, run_id)
    evidence = {
        "run": run_id,
        "notes": notes.read_text(encoding="utf-8") if notes.is_file() else "",
        "comments": comments(directory),
    }
    target = paths.round_dir(round_id) / "human" / f"{run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return evidence


def summary(round_id: str, run_id: str) -> dict:
    evidence = export(round_id, run_id)
    open_comments = [c for c in evidence["comments"] if c["status"] == "open"]
    return {
        "run": run_id,
        "notes": bool(evidence["notes"].strip()),
        "comments": len(evidence["comments"]),
        "open_comments": len(open_comments),
    }
