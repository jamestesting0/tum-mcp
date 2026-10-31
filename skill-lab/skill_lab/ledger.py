"""The tracked lesson ledger: sanitized round entries that later rounds read first."""

import re
from datetime import UTC, datetime
from pathlib import Path

from skill_lab import LabError, paths, rounds

REQUIRED_SECTIONS = ("## Weakness", "## Edits", "## Lesson", "## Decision")
PROBLEMS = (
    (re.compile(r"https?://\S*(tum\.de|tum\.live|moodle|zulip|artemis)", re.I), "campus URL"),
    (re.compile(r"(/Users/|/home/|[A-Za-z]:\\\\)"), "absolute local path"),
    (re.compile(r"^\s*>", re.M), "quoted passage"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "email address"),
    (re.compile(r"\.omo/"), "path into local lab state"),
)


def problems(text: str) -> list[str]:
    found = [label for pattern, label in PROBLEMS if pattern.search(text)]
    found += [f"missing section {s!r}" for s in REQUIRED_SECTIONS if s not in text]
    return found


def entry(round_id: str, decision: str) -> str:
    config = rounds.load(round_id)
    author = ":".join(config["roles"]["author"].values())
    judge = ":".join(config["roles"]["judge"].values())
    body = decision.strip().replace("\n## ", "\n### ")
    if body.startswith("## "):
        body = "#" + body
    date = datetime.now(UTC).date().isoformat()
    return (
        f"\n## {round_id} ({date})\n\n"
        f"- scenario: {config['scenario']}; confirm: {config.get('confirm_scenario')}\n"
        f"- author: {author}; probe judge: {judge}\n"
        f"- base: {config['base']['ref'][:12]} + {len(config['base']['patches'])} patch(es)\n\n"
        f"{body}\n"
    )


def add(round_id: str, decision_file: Path, ledger: Path | None = None) -> str:
    text = decision_file.read_text(encoding="utf-8")
    found = problems(text)
    if found:
        raise LabError("The decision cannot enter the tracked ledger: " + "; ".join(found))
    target = ledger or paths.LEDGER
    addition = entry(round_id, text)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(addition)
    return addition
