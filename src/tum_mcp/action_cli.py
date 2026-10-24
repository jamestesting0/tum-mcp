"""Read-only action reviews. This build cannot issue trusted grants or submit."""

from pathlib import Path
from typing import Literal

import typer

from tum_mcp.action_preflight import Preflight
from tum_mcp.approvals import Approvals
from tum_mcp.artemis import Artemis
from tum_mcp.credentials import Vault
from tum_mcp.settings import Provider, find_account
from tum_mcp.transport import API
from tum_mcp.workspace import workflow_status

app = typer.Typer(no_args_is_help=True)


@app.command("review-start")
def review_start(
    account_id: str,
    course_id: int,
    exercise_id: int,
    mode: Literal["graded", "practice"] = "graded",
) -> None:
    """Explain the prospective target. No grant is issued and participation is not started."""
    provider = Artemis(API(find_account(account_id, Provider.ARTEMIS)))
    typer.echo(Preflight(provider).start(course_id, exercise_id, mode).model_dump_json(indent=2))


@app.command("review-submit")
def review_submit(workspace: Path) -> None:
    """Review an exact revision with full local-test evidence; performs no push."""
    workflow = workflow_status(workspace)
    provider = Artemis(API(find_account(workflow.account_id, Provider.ARTEMIS)))
    typer.echo(Preflight(provider).submit(workspace).model_dump_json(indent=2))


@app.command("status")
def action_status(fingerprint: str) -> None:
    """Read an existing encrypted attempt receipt without retrying an operation."""
    typer.echo(Approvals(Vault()).read(fingerprint).model_dump_json(indent=2))
