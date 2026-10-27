"""Explicit browser access and project collection commands."""

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import studocu_enabled

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def require_enabled() -> None:
    if not studocu_enabled():
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Install the Studocu extension first.")


@app.command()
def connect() -> None:
    """Explain the supported browser access route without collecting credentials."""
    require_enabled()
    typer.echo(
        "Sign in to Studocu in your own browser. Save originals there, then use studocu import. "
        "No browser session is copied."
    )


@app.command()
def logout() -> None:
    """Explain browser logout; there is no separate saved Studocu credential."""
    require_enabled()
    typer.echo("No Studocu credential is stored by TUM MCP. Sign out in your browser if desired.")


@app.command("plan")
def plan_command(project: Path, selection: Annotated[Path, typer.Option("--selection")]) -> None:
    """Create or resume a reviewed selection from a local JSON file."""
    require_enabled()
    from tum_mcp.studocu.state import plan

    typer.echo(plan(project, selection).model_dump_json(indent=2))


@app.command("status")
def status_command(
    project: Path, json_output: Annotated[bool, typer.Option("--json")] = False
) -> None:
    """Show selected documents and the partial discovery boundary."""
    require_enabled()
    from tum_mcp.studocu.state import load_discovery, load_queue
    from tum_mcp.study_store import load_state

    root = project.expanduser().resolve()
    queue = load_queue(root)
    discovery = load_discovery(root)
    state = load_state(root)
    counts = {
        name: sum(item.state == name for item in queue.documents)
        for name in (
            "pending",
            "acquiring",
            "action_required",
            "downloaded",
            "imported",
            "duplicate",
            "unavailable",
            "failed",
            "outcome_unknown",
        )
    }
    if not json_output:
        from tum_mcp.ui import State, heading, status_rows, terminal_console

        console = terminal_console()
        heading(console, "Studocu collection", "Selected supplementary materials for this course.")
        status_rows(
            console,
            [
                (
                    "Selected",
                    State.INFO,
                    f"{sum(item.decision == 'include' for item in queue.documents)} document(s).",
                ),
                (
                    "Imported",
                    State.READY if counts["imported"] else State.INFO,
                    f"{counts['imported']} document(s) imported.",
                ),
                (
                    "Needs action",
                    State.ACTION if counts["action_required"] else State.INFO,
                    f"{counts['action_required']} browser action(s) pending.",
                ),
                (
                    "Failed",
                    State.FAILED if counts["failed"] else State.INFO,
                    f"{counts['failed']} document(s).",
                ),
            ],
        )
        console.print("Discovery is partial. Use --json for document and recovery details.")
        return
    typer.echo(
        json.dumps(
            {
                "selection": queue.model_dump(mode="json"),
                "discovered": len(discovery.documents) if discovery else 0,
                "selected": sum(item.decision == "include" for item in queue.documents),
                "decisions": {
                    decision: sum(item.decision == decision for item in queue.documents)
                    for decision in ("include", "exclude", "review")
                },
                "counts": counts,
                "validated_current": sum(
                    item.resource.studocu is not None and item.status == "current"
                    for item in state.resources
                ),
                "discovery": "partial",
                "text_coverage": "not_tracked",
            },
            indent=2,
        )
    )


@app.command("mark")
def mark_command(
    project: Path,
    document_id: Annotated[str, typer.Option("--document-id")],
    state: Annotated[
        Literal["pending", "acquiring", "unavailable", "outcome_unknown", "failed"],
        typer.Option("--state"),
    ],
) -> None:
    """Record an observed browser outcome without contacting Studocu."""
    require_enabled()
    from tum_mcp.studocu.state import mark_outcome

    typer.echo(mark_outcome(project, document_id, state).model_dump_json(indent=2))


@app.command("stage")
def stage_command(
    project: Path,
    document_id: Annotated[str, typer.Option("--document-id")],
    file: Annotated[Path, typer.Option("--file")],
) -> None:
    """Validate and stage a user-selected original for a later MCP import."""
    require_enabled()
    from tum_mcp.studocu.imports import stage, staged_validation

    name = stage(project, document_id, file)
    typer.echo(
        json.dumps(
            {
                "staged_name": name,
                "validation": staged_validation(project, name),
                "identity_basis": "user_selected_file",
            }
        )
    )


@app.command("import")
def import_command(
    project: Path,
    document_id: Annotated[str, typer.Option("--document-id")],
    file: Annotated[Path, typer.Option("--file")],
) -> None:
    """Import one browser-saved original chosen for a selected document."""
    require_enabled()
    from tum_mcp.studocu.imports import import_staged, stage

    typer.echo(
        json.dumps(import_staged(project, document_id, stage(project, document_id, file)), indent=2)
    )
