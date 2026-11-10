"""Dated learning events tied to course items, and the short brief computed from them.

The record holds observations (attempts, mistakes with the course rule that corrects them,
the next plan), never chat text or inferred ability. Consent is given once, at the course's
first setup; while it is off nothing is written.
"""

import json
import secrets
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from tum_mcp.course.project.store import private_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
Outcome = Literal["solved", "hint", "wrong", "skipped"]
# Days until an item comes back after a miss, then after each later success.
INTERVALS = (1, 3, 7, 14, 30)
BRIEF_BYTES = 1200
USE = [
    "Dated evidence about this student; course sources decide what is correct.",
    "Use it for this request only; do not mention it elsewhere.",
    "Without asking, record what happens in this chat, in your words, never theirs:"
    " study learner note . --item ID --outcome solved|hint|wrong|skipped [--note TEXT];"
    " mistake . --item ID --note RULE [--source KEY], naming the rule broken, not their claim;"
    " resolve . MISTAKE_ID; plan . TEXT.",
    "End with one line saying what you noted. 'What do you know about me?': study learner"
    " show . 'Forget ...': study learner forget . --item ID (or an event id, or --all).",
]


class Consent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["on", "off"]
    decided: date
    via: Literal["setup", "command"]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    at: date
    kind: Literal["attempt", "mistake", "resolved", "plan"]
    item: str | None = None
    outcome: Outcome | None = None
    note: Note = ""
    source: str | None = None
    ref: str | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""


def _consent_path(root: Path) -> Path:
    return private_path(root, "learner/consent.json")


def _events_path(root: Path) -> Path:
    return private_path(root, "learner/events.jsonl")


def decided(root: Path) -> bool:
    return _consent_path(root).is_file()


def consent(root: Path) -> str:
    path = _consent_path(root)
    return Consent.model_validate_json(path.read_bytes()).state if path.is_file() else "off"


def set_consent(root: Path, state: Literal["on", "off"], via: Literal["setup", "command"]) -> dict:
    path = _consent_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = Consent(state=state, decided=date.today(), via=via)
    private_write(path, value.model_dump_json().encode())
    return {"learner": state}


def events(root: Path) -> list[Event]:
    path = _events_path(root)
    if not path.is_file():
        return []
    return [Event.model_validate_json(line) for line in path.read_text().splitlines() if line]


def _save(root: Path, rows: list[Event]) -> None:
    path = _events_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    private_write(
        path, "".join(row.model_dump_json(exclude_defaults=True) + "\n" for row in rows).encode()
    )


def _graph(root: Path):
    from tum_mcp.course.memory.projection import project
    from tum_mcp.course.memory.store import read_inputs

    return project(read_inputs(root))


def resolve_item(graph, value: str) -> str:
    """A full item id, or a unique id suffix such as `problem-1-2-2` or `concept/cnf`."""
    value = value.strip().strip("/")
    if value in graph.nodes:
        return value
    found = [ref for ref in graph.nodes if ref.endswith("/" + value)]
    if len(found) == 1:
        return found[0]
    detail = f" Candidates: {', '.join(sorted(found)[:5])}." if found else ""
    raise CampusError(Code.ACTION_REQUIRED, f"No single course item matches {value!r}.{detail}")


def _day(on: date | None) -> date:
    today = date.today()
    if on is not None and on > today:
        raise CampusError(Code.ACTION_REQUIRED, "A learning event cannot be in the future.")
    return on or today


def record(
    root: Path,
    kind: Literal["attempt", "mistake", "resolved", "plan"],
    *,
    item: str | None = None,
    outcome: Outcome | None = None,
    note: str = "",
    source: str | None = None,
    ref: str | None = None,
    text: str = "",
    on: date | None = None,
) -> dict:
    if consent(root) != "on":
        raise CampusError(Code.ACTION_REQUIRED, "The learning record is off for this course.")
    rows = events(root)
    if kind in {"attempt", "mistake"}:
        graph = _graph(root)
        item = resolve_item(graph, item or "")
        if source is not None:
            key = source.removeprefix("source/")
            if f"source/{key}" not in graph.nodes:
                raise CampusError(Code.ACTION_REQUIRED, f"Unknown course source {source!r}.")
            source = key
    if kind == "resolved" and not any(row.id == ref and row.kind == "mistake" for row in rows):
        raise CampusError(Code.ACTION_REQUIRED, f"No recorded mistake {ref!r}.")
    event = Event(
        id=secrets.token_hex(4),
        at=_day(on),
        kind=kind,
        item=item,
        outcome=outcome,
        note=note,
        source=source,
        ref=ref,
        text=text,
    )
    same = next(
        (
            row
            for row in rows
            if (row.kind, row.item, row.outcome, row.at, row.ref)
            == (kind, item, outcome, event.at, ref)
            and kind != "plan"
        ),
        None,
    )
    if same is not None:
        return {"id": same.id, "recorded": False}
    _save(root, [*rows, event])
    return {"id": event.id, "recorded": True}


def forget(
    root: Path,
    *,
    event: str | None = None,
    item: str | None = None,
    before: date | None = None,
    everything: bool = False,
) -> dict:
    rows = events(root)

    def gone(row: Event) -> bool:
        if everything:
            return True
        if event is not None and event in {row.id, row.ref}:
            return True
        if item is not None and row.item is not None:
            needle = item.strip("/")
            if row.item == needle or row.item.endswith("/" + needle) or f"/{needle}/" in row.item:
                return True
        return before is not None and row.at < before

    removed = {row.id for row in rows if gone(row)}
    kept = [row for row in rows if row.id not in removed and row.ref not in removed]
    _save(root, kept)
    return {"forgotten": len(rows) - len(kept), "kept": len(kept)}


def due(rows: list[Event], today: date) -> dict[str, tuple[date, str]]:
    level: dict[str, int] = {}
    nxt: dict[str, tuple[date, str]] = {}
    for row in sorted((r for r in rows if r.kind == "attempt" and r.item), key=lambda r: r.at):
        if row.outcome in {"hint", "wrong"}:
            level[row.item] = 0
        elif row.outcome == "solved" and row.item in level:
            level[row.item] = min(level[row.item] + 1, len(INTERVALS) - 1)
        else:
            continue
        nxt[row.item] = (row.at + timedelta(days=INTERVALS[level[row.item]]), row.outcome)
    return {item: value for item, value in nxt.items() if value[0] <= today}


def brief(root: Path) -> dict:
    if consent(root) != "on":
        return {"learner": "off"}
    rows = events(root)
    today = date.today()
    graph = _graph(root) if rows else None

    def title(ref: str) -> str:
        node = graph.nodes.get(ref) if graph else None
        return (node.title or ref) if node else ref

    closed = {row.ref for row in rows if row.kind == "resolved"}
    mistakes = [row for row in rows if row.kind == "mistake" and row.item and row.id not in closed]
    mistakes.sort(key=lambda row: row.at, reverse=True)
    open_rows = []
    for row in mistakes[:3]:
        review = [
            {"item": edge.start, "title": title(edge.start)}
            for edge in (graph.edges if graph else ())
            if edge.end == row.item and edge.relation == "prerequisite_of"
        ][:2]
        open_rows.append(
            {
                "id": row.id,
                "item": row.item,
                "title": title(row.item),
                "at": row.at.isoformat(),
                "rule": row.note,
                "source": row.source,
                "review": review,
            }
        )
    revisit = [
        {"item": item, "title": title(item), "last": last, "due": when.isoformat()}
        for item, (when, last) in sorted(due(rows, today).items(), key=lambda kv: kv[1][0])
    ][:5]
    plans = [row for row in rows if row.kind == "plan"]
    recent = [
        row for row in rows if row.kind == "attempt" and (today - row.at).days <= 14 and row.outcome
    ]
    result: dict = {
        "learner": "on",
        "today": today.isoformat(),
        "open_mistakes": open_rows,
        "due": revisit,
        "plan": {"at": plans[-1].at.isoformat(), "text": plans[-1].text} if plans else None,
        "last_14_days": {
            outcome: sum(row.outcome == outcome for row in recent)
            for outcome in ("solved", "hint", "wrong")
        },
        "use": USE,
    }
    for key in ("last_14_days", "plan", "due", "open_mistakes"):
        while len(json.dumps(result, ensure_ascii=False)) > BRIEF_BYTES:
            value = result[key]
            if isinstance(value, list) and value:
                value.pop()
            elif value is not None and not isinstance(value, list):
                result[key] = None
            else:
                break
    return result


def show(root: Path) -> dict:
    rows = events(root)
    return {
        "learner": consent(root),
        "events": [row.model_dump(mode="json", exclude_defaults=True) for row in rows],
        "oldest": min((row.at for row in rows), default=None),
        "where": str(_events_path(root).relative_to(root)),
    }
