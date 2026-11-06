"""User-facing first-publish approval and local publishing controls."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from filelock import FileLock

from tum_mcp.course.app.publish_models import load_publication, repository_name, save_publication
from tum_mcp.course.content.store import present
from tum_mcp.course.project.store import load_state, private_path
from tum_mcp.errors import CampusError, Code

app = typer.Typer(invoke_without_command=True, pretty_exceptions_show_locals=False)


def report(result_json: str, status: str) -> None:
    typer.echo(result_json)
    if status in {"pending", "failed"}:
        raise typer.Exit(2)


@app.callback()
def setup(
    context: typer.Context,
    project: Annotated[
        Path, typer.Option(help="Course project; defaults to the current folder.")
    ] = Path("."),
    repository: Annotated[str | None, typer.Option(help="Optional OWNER/NAME override.")] = None,
    public_site: Annotated[
        bool,
        typer.Option(
            "--public-site", help="Authorize public website content in a private repository."
        ),
    ] = False,
    wait_seconds: Annotated[int, typer.Option(min=0, max=60)] = 60,
) -> None:
    """Preview publication; add --public-site to create a private repository and publish."""
    if context.invoked_subcommand is not None:
        return
    from tum_mcp.course.app.publish import build_for_publication, configure, publish

    root = project.expanduser().resolve()
    existing = load_publication(root)
    if existing is None and not public_site:
        course = load_state(root).course
        typer.echo(
            json.dumps(
                {
                    "repository": repository,
                    "suggested_name": repository_name(course),
                    "repository_visibility": "private",
                    "website_visibility": "public",
                    "workspaces": [
                        workspace
                        for workspace in ("study", "exercises", "lectures", "exam")
                        if present(root, workspace)
                    ],
                    "authentication": "Host GitHub CLI: gh auth login --hostname github.com",
                    "requires": "An eligible paid GitHub plan for Pages from private repositories.",
                    "next": "Review website contents, then rerun with --public-site to publish.",
                },
                indent=2,
            )
        )
        return
    if (
        existing is not None
        and repository is not None
        and repository.casefold() != existing.repository.casefold()
    ):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "This course already has a publishing repository."
        )
    if existing is not None and existing.schema_version != 2 and not public_site:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Confirm --public-site to publish all prepared workspaces instead of the saved "
            "selective scope.",
        )
    # Keep snapshot preparation and upload ordered with competing automatic publications.
    with FileLock(str(private_path(root, "publish.lock")), is_singleton=True):
        site = build_for_publication(root)
        configure(root, repository=repository, site=site)
        result = publish(root, wait_seconds=wait_seconds, site=site, verify_unchanged=True)
    report(json.dumps(asdict(result), indent=2), result.status)


@app.command()
def sync(
    project: Path,
    wait_seconds: Annotated[int, typer.Option(min=0, max=60)] = 60,
) -> None:
    """Retry or update a configured study site's repository and deployment."""
    from tum_mcp.course.app.publish import publish

    result = publish(project, wait_seconds=wait_seconds, verify_unchanged=True)
    report(json.dumps(asdict(result), indent=2), result.status)


@app.command()
def status(project: Path) -> None:
    """Show saved repository, hosted URL and deployment state without network calls."""
    publication = load_publication(project.expanduser().resolve())
    typer.echo(publication.model_dump_json(indent=2) if publication else "null")


@app.command()
def pause(project: Path) -> None:
    """Pause automatic uploads; the existing hosted site remains available."""
    root = project.expanduser().resolve()
    publication = load_publication(root)
    if publication is None:
        raise CampusError(Code.ACTION_REQUIRED, "No publication is configured for this course.")
    save_publication(root, publication.model_copy(update={"auto_sync": False}))
    typer.echo("Automatic publication paused. Use publish resume to enable it again.")


@app.command()
def resume(project: Path) -> None:
    """Resume uploads after future builds, using the existing publication consent."""
    root = project.expanduser().resolve()
    publication = load_publication(root)
    if publication is None:
        raise CampusError(Code.ACTION_REQUIRED, "Configure publication before enabling uploads.")
    save_publication(root, publication.model_copy(update={"auto_sync": True}))
    typer.echo("Automatic publication resumes after the next study build.")
