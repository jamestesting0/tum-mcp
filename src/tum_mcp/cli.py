"""Local settings and onboarding commands; never runs automatically on npm install."""

import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from tum_mcp import __version__
from tum_mcp.commands.discovery import discover
from tum_mcp.commands.help import configure_help
from tum_mcp.connect import ServiceChoice
from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import (
    audio_notes_enabled,
    course_memory_enabled,
    lecture_enabled,
    video_notes_enabled,
)
from tum_mcp.moodle.browsers import BrowserSetupError
from tum_mcp.moodle.errors import MoodleError
from tum_mcp.settings import preferences

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False, add_completion=False)
skills_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(skills_app, name="skills", help="List, inspect and customize workflow skills.")
from tum_mcp.tumonline.manage import app as manage_app  # noqa: E402

app.add_typer(
    manage_app, name="manage", help="Manage TUMonline permissions and saved browser profiles."
)
from tum_mcp.commands.browser_profiles import manage_browsers  # noqa: E402

manage_app.command("browsers")(manage_browsers)
from tum_mcp.course.cli import app as study_app  # noqa: E402

app.add_typer(study_app, name="study", help="Prepare, preview and publish a course app.")
from tum_mcp.course.review.cli import app as review_app  # noqa: E402

app.add_typer(review_app, name="review", help="Review prepared course content in gated rounds.")
from tum_mcp.course.lecture.cli import app as lecture_app  # noqa: E402

app.add_typer(
    lecture_app,
    name="lecture",
    help="Prepare lecture recordings (Lecture workflow).",
)
from tum_mcp.course.media.video_cli import app as video_app  # noqa: E402

app.add_typer(
    video_app,
    name="video-notes",
    help="Render and maintain explainer videos (Video Notes workflow).",
)
from tum_mcp.course.media.audio_cli import app as audio_app  # noqa: E402

app.add_typer(
    audio_app,
    name="audio-notes",
    help="Assemble and publish revision audio (Audio Notes workflow).",
)


def print_version(requested: bool) -> None:
    if requested:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def root(
    _version: Annotated[
        bool,
        typer.Option(
            "--version", callback=print_version, is_eager=True, help="Show the installed version."
        ),
    ] = False,
) -> None:
    """Campus tools and local study workflows."""


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)


@app.command()
def serve() -> None:
    """Run the MCP server over stdio (started by coding apps)."""
    os.environ["TUM_MOODLE_SESSION_STORAGE"] = "file"
    from tum_mcp.server import server

    logging.getLogger("httpx2").setLevel(logging.WARNING)
    from tum_mcp.runtime_leases import runtime_lease

    with runtime_lease():
        server.run()


@app.command(hidden=True)
def status(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable configuration.")
    ] = False,
) -> None:
    """Compatibility alias for doctor; --json retains the previous configuration format."""
    from tum_mcp.diagnostics import collect_services

    if not json_output:
        doctor()
        return
    report = collect_services()
    typer.echo(
        json.dumps(
            {
                "version": __version__,
                "state": "configured_not_live_verified",
                "read_access": "server_permissions",
                "accounts": [
                    account.model_dump(mode="json") | {"account_id": account.id}
                    for account in preferences().accounts
                ],
                "remote_actions": "disabled",
                "extensions": {
                    "lecture": lecture_enabled(),
                    "audio-notes": audio_notes_enabled(),
                    "video-notes": video_notes_enabled(),
                    "course-memory": course_memory_enabled(),
                },
                "registry": "not_checked",
                "services": [item.model_dump(mode="json") for item in report.services],
                "issues": [item.model_dump(mode="json") for item in report.issues],
            },
            indent=2,
        )
    )


@app.command("login")
def connect() -> None:
    """Sign in to the campus services you choose."""
    from rich.text import Text

    from tum_mcp.commands.browser_profiles import choose_login_browser
    from tum_mcp.commands.ui import State, heading, hint, select_services, terminal_console
    from tum_mcp.connect import SIGN_IN_MINUTES, ConnectionResult, connect_services
    from tum_mcp.moodle.browsers import discover_browsers

    console = terminal_console()
    if not sys.stdin.isatty():
        raise CampusError(Code.ACTION_REQUIRED, "Run tum-mcp login in an interactive terminal.")
    heading(console, "Login")
    try:
        selected = select_services()
        if not selected:
            console.print("No services selected. Nothing was changed.")
            return
        browser = choose_login_browser(discover_browsers())
    except (KeyboardInterrupt, EOFError):
        console.print("Cancelled. No browser was opened.")
        raise typer.Exit(130) from None
    names = ", ".join(value.label for value in selected)
    console.print()
    console.print(Text(f"Opening {names} in {browser.login_label}."))
    console.print("Sign in there and complete MFA.")
    if browser.windows_host:
        console.print("Preparing the private Windows browser driver (first use only).")
    hint(console, f"Waiting up to {SIGN_IN_MINUTES} minutes. Press Ctrl+C to stop waiting.")
    hint(console, "Completed connections are saved.")
    console.print()
    pending = dict.fromkeys(selected)

    def connected(result: ConnectionResult) -> None:
        del pending[result.service]
        console.print(
            Text.assemble((State.READY.symbol + " ", "ready"), f"{result.service.label} connected")
        )
        if result.service == ServiceChoice.TUMONLINE:
            hint(console, "  Choose what your agent may read: tum-mcp manage tumonline")
        if pending:
            remaining = ", ".join(service.label for service in pending)
            hint(console, f"  Waiting for {remaining}")

    try:
        results = connect_services(selected, on_connected=connected, browser=browser)
    except KeyboardInterrupt:
        console.print("Cancelled. Completed connections were saved.")
        raise typer.Exit(130) from None
    console.print()
    if results:
        console.print(
            "Next: ask your coding agent about your courses, "
            "for example \u201cWhat is due this week?\u201d"
        )


app.command("connect", hidden=True)(connect)


app.command()(discover)


@app.command()
def logout(
    service: Annotated[
        ServiceChoice | None,
        typer.Argument(
            metavar="[SERVICE]",
            help="moodle, artemis, zulip, tumonline or tum_live; omit to choose.",
            show_default=False,
        ),
    ] = None,
    account_id: Annotated[
        str | None,
        typer.Argument(
            metavar="[ACCOUNT]",
            help="Needed only when several accounts of the service are saved.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Remove saved campus connections from this computer."""
    from tum_mcp.logout import choose_logout, logout_named

    if service is None:
        choose_logout()
        return
    logout_named(service, account_id)


@app.command()
def doctor(
    refresh_clients: Annotated[
        bool,
        typer.Option(
            "--refresh-clients", help="Recheck clients even when their 24-hour cache is fresh."
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable diagnostics.")
    ] = False,
    live: Annotated[
        bool,
        typer.Option(
            "--live/--static",
            help="Verify saved campus sessions and optional GitHub authentication.",
        ),
    ] = True,
) -> None:
    """Check connections, workflows, coding apps and the runtime."""
    from collections import Counter

    from rich.status import Status
    from rich.text import Text

    from tum_mcp.commands.ui import (
        State,
        count,
        heading,
        hint,
        next_steps,
        section,
        status_rows,
        terminal_console,
    )
    from tum_mcp.diagnostics import collect_diagnostics

    if refresh_clients and not live:
        raise typer.BadParameter("--refresh-clients requires live checks; omit --static.")
    console = terminal_console()
    if json_output or not console.is_terminal:
        report = collect_diagnostics(live=live, refresh_clients=refresh_clients)
    else:
        with Status("Checking…", console=console):
            report = collect_diagnostics(live=live, refresh_clients=refresh_clients)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return
    heading(
        console,
        "Doctor",
        None if live else "Sessions, coding apps and GitHub were not checked live.",
        version=True,
    )
    sections = (
        ("Services", report.services),
        ("Workflows", report.extensions),
        ("Coding apps", report.clients),
        ("Runtime", report.runtime),
    )
    attention = sum(
        item.state in {State.ACTION, State.FAILED} for _, items in sections for item in items
    )
    if attention:
        console.print(
            Text.assemble(
                (State.ACTION.symbol + " ", "attention"),
                count(attention, "item needs", "items need") + " attention",
            )
        )
    else:
        verdict = "Ready" if live else "No problems found"
        console.print(Text.assemble((State.READY.symbol + " ", "ready"), verdict))
    console.print()
    next_steps(console, list(report.next_steps))
    for title, items in sections:
        rows = [item for item in items if item.state != State.INFO]
        notes = [item for item in items if item.state == State.INFO]
        if not items:
            continue
        section(console, title)
        repeated = {
            detail
            for detail, number in Counter(item.detail for item in rows).items()
            if number > 1 and detail
        }
        status_rows(
            console,
            [
                (item.label, item.state, "" if item.detail in repeated else item.detail)
                for item in rows
            ],
        )
        for line in [*sorted(repeated), *(f"{note.label}: {note.detail}" for note in notes)]:
            hint(console, line)
        if repeated or notes:
            console.print()
    next_steps(console, list(report.optional_steps), "Optional")


from tum_mcp.commands.lifecycle import install, setup, uninstall, update  # noqa: E402

app.command()(setup)
app.command()(install)
app.command()(update)
app.command()(uninstall)


@skills_app.command("list")
def list_skills(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable skill metadata.")
    ] = False,
) -> None:
    """List the skills your coding apps use."""
    import re
    import textwrap

    from tum_mcp.skills import inspect_skills

    def summary(description: str) -> str:
        first = re.split(r" - |\. ", description)[0].rstrip(".")
        return textwrap.shorten(first, 72, placeholder="…")

    skills = inspect_skills()
    if json_output:
        typer.echo(json.dumps(skills, indent=2))
        return
    from tum_mcp.commands.ui import detail_rows, heading, hint, terminal_console

    console = terminal_console()
    heading(console, "Skills")
    detail_rows(
        console,
        [
            (
                item["name"],
                summary(item["description"]) + (" (customized)" if item["customized"] else ""),
            )
            for item in skills
        ],
    )
    hint(console, "Read one: tum-mcp skills inspect NAME")


@skills_app.command()
def customize(name: str) -> None:
    """Create your own editable copy of a skill."""
    from tum_mcp.skills import customize_skill

    typer.echo(str(customize_skill(name)))


@skills_app.command("export", rich_help_panel="Advanced")
def export_skills(destination: Path) -> None:
    """Copy the active skills to a new folder for manual installation."""
    from tum_mcp.skills import export_pack

    export_pack(destination)
    typer.echo(str(destination))


@skills_app.command("validate")
def validate_skill_pack(
    all_skills: Annotated[
        bool,
        typer.Option("--all", help="Include packaged optional workflows without installing them."),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable validation.")
    ] = False,
) -> None:
    """Check skill metadata and the tools each skill names."""
    from tum_mcp.skills.validation import validate_skills

    report = validate_skills(include_optional=all_skills)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        from rich.text import Text

        from tum_mcp.commands.ui import State, count, heading, terminal_console

        console = terminal_console()
        heading(console, "Validate skills")
        checked = count(len(report.checked_skills), "skill")
        if report.errors:
            console.print(
                Text.assemble(
                    (State.FAILED.symbol + " ", "failed"),
                    f"{count(len(report.errors), 'problem')} in {checked}",
                )
            )
            for error in report.errors:
                console.print(Text(f"  {error}"))
        else:
            console.print(Text.assemble((State.READY.symbol + " ", "ready"), f"{checked} valid"))
    if report.errors:
        raise typer.Exit(1)


@skills_app.command("inspect")
def inspect_skill(name: str) -> None:
    """Print a skill as your coding apps read it."""
    from tum_mcp.skills import selected

    typer.echo((selected(name) / "SKILL.md").read_text(encoding="utf-8"))


@skills_app.command("diff")
def diff_skill(name: str) -> None:
    """Show how your customized skill differs from the bundled one."""
    from tum_mcp.skills import skill_diff

    typer.echo(skill_diff(name) or "No entry-text difference from the bundled skill.")


@skills_app.command("evaluate", rich_help_panel="Advanced")
def evaluate_skills(trials: Path) -> None:
    """Score saved trial records of skill use."""
    from tum_mcp.evaluations import score_trials

    typer.echo(json.dumps([score.model_dump() for score in score_trials(trials)], indent=2))


configure_help(app)


def main() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if isinstance(stream, io.TextIOWrapper):
                stream.reconfigure(encoding="utf-8")
    try:
        app(prog_name="tum-mcp")
    except (CampusError, MoodleError) as error:
        typer.echo(f"Error: {error.message}", err=True)
        raise SystemExit(2) from None
    except BrowserSetupError as error:
        typer.echo(f"Error: {error}", err=True)
        raise SystemExit(2) from None
    except OSError as error:
        reason = error.strerror or type(error).__name__
        where = f" ({error.filename})" if error.filename else ""
        typer.echo(
            f"Error: local files could not be accessed: {reason}{where}. "
            "Check their permissions and retry.",
            err=True,
        )
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        typer.echo("Cancelled. Completed changes were preserved.", err=True)
        raise SystemExit(130) from None
