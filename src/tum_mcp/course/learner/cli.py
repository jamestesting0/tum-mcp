import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from tum_mcp.course.learner import record
from tum_mcp.course.learner.record import Outcome

app = typer.Typer(pretty_exceptions_show_locals=False)
On = Annotated[datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Day it happened.")]


def _day(value: datetime | None) -> date | None:
    return value.date() if value else None


def _echo(value: dict) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, default=str))


@app.command()
def brief(project: Path) -> None:
    """This student's open mistakes, items due again and last plan, for a study request."""
    _echo(record.brief(project.resolve()))


@app.command()
def enable(project: Path) -> None:
    """Start recording, when the student asks."""
    _echo(record.set_consent(project.resolve(), "on", "command"))


@app.command()
def disable(project: Path) -> None:
    """Stop recording, when the student asks; existing events stay until forgotten."""
    _echo(record.set_consent(project.resolve(), "off", "command"))


@app.command()
def note(
    project: Path,
    item: Annotated[str, typer.Option(help="Course item id or a unique suffix.")],
    outcome: Annotated[Outcome, typer.Option()],
    note: Annotated[str, typer.Option(help="Your own words, at most 160 characters.")] = "",
    on: On = None,
) -> None:
    """Record an attempt this student made in the chat."""
    _echo(
        record.record(
            project.resolve(), "attempt", item=item, outcome=outcome, note=note, on=_day(on)
        )
    )


@app.command()
def mistake(
    project: Path,
    item: Annotated[str, typer.Option(help="Course item id or a unique suffix.")],
    note: Annotated[str, typer.Option(help="The misconception, at most 160 characters.")],
    source: Annotated[str | None, typer.Option(help="Source key of the correcting rule.")] = None,
    on: On = None,
) -> None:
    """Record a misconception and the course source that corrects it."""
    _echo(
        record.record(
            project.resolve(), "mistake", item=item, note=note, source=source, on=_day(on)
        )
    )


@app.command()
def resolve(project: Path, mistake_id: str) -> None:
    """Close a mistake the student has now got right; its history is kept."""
    _echo(record.record(project.resolve(), "resolved", ref=mistake_id))


@app.command()
def plan(project: Path, text: str) -> None:
    """Record the next study step agreed in this chat."""
    _echo(record.record(project.resolve(), "plan", text=text))


@app.command()
def show(project: Path) -> None:
    """Everything recorded about this student in this course."""
    _echo(record.show(project.resolve()))


@app.command()
def forget(
    project: Path,
    event: Annotated[str | None, typer.Argument(help="Event id.")] = None,
    item: Annotated[
        str | None, typer.Option(help="Item id, suffix or set such as sheet-1.")
    ] = None,
    before: Annotated[datetime | None, typer.Option(formats=["%Y-%m-%d"])] = None,
    everything: Annotated[bool, typer.Option("--all")] = False,
) -> None:
    """Delete recorded events for good."""
    if not (event or item or before or everything):
        raise typer.BadParameter("Name an event, --item, --before or --all.")
    _echo(
        record.forget(
            project.resolve(), event=event, item=item, before=_day(before), everything=everything
        )
    )
