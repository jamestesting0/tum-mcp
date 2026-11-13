"""Register, finish or pause one course request in the current Codex thread."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from tum_mcp.course.checks.batch import Batch
from tum_mcp.course.project.models import Key
from tum_mcp.course.project.store import private_path, read_bytes
from tum_mcp.course.workflow import tasks
from tum_mcp.course.workflow.hooks import Host, handle
from tum_mcp.errors import CampusError, Code

app = typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
def start(
    project: Path,
    batch: Annotated[str, typer.Option(help="Batch ID for .tum-mcp/batches/<ID>.json.")],
    review_rounds: Annotated[int, typer.Option(min=0, max=20)] = 0,
    owner: Annotated[str | None, typer.Option(help="Identity supplied by the host hook.")] = None,
) -> None:
    """Track the requested batch; add review rounds only when already authorized."""
    root = project.resolve()
    path = f".tum-mcp/batches/{batch}.json"
    try:
        batch_id = TypeAdapter(Key).validate_python(batch)
        body = read_bytes(private_path(root, f"batches/{batch_id}.json"))
        if body is None:
            raise CampusError(
                Code.ACTION_REQUIRED, f"Missing {path}; see tum-mcp study schema batch."
            )
        Batch.model_validate_json(body)
    except ValidationError as exc:
        raise CampusError(
            Code.ACTION_REQUIRED, f"Invalid {path}; see tum-mcp study schema batch."
        ) from exc
    typer.echo(tasks.begin(root, batch_id, review_rounds, owner=owner).model_dump_json())


@app.command()
def finish(project: Path, owner: Annotated[str | None, typer.Option()] = None) -> None:
    """Check the full draft and any authorized review before handing off."""
    typer.echo(json.dumps(tasks.finish(project.resolve(), owner=owner)))


@app.command()
def pause(
    project: Path,
    reason: Annotated[str, typer.Option()],
    owner: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Honor a user pause or record a concrete blocker that requires their input."""
    typer.echo(tasks.pause(project.resolve(), reason, owner=owner).model_dump_json())


@app.command(name="hook", hidden=True)
def hook(host: Host = "codex", event: str | None = None) -> None:
    """Read the host Stop event; print its local continuation decision."""
    typer.echo(json.dumps(handle(host, json.load(sys.stdin), event)))
