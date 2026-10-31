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
from tum_mcp.cli_help import configure_help
from tum_mcp.credentials import Vault
from tum_mcp.discovery_cli import discover
from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import (
    audio_notes_enabled,
    lecture_enabled,
    video_notes_enabled,
)
from tum_mcp.moodle.browsers import BrowserSetupError
from tum_mcp.moodle.errors import MoodleError
from tum_mcp.settings import (
    Provider,
    find_account,
    preferences,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False, add_completion=False)
skills_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(skills_app, name="skills", help="Inspect and validate workflow skills.")
from tum_mcp.tumonline.manage import app as manage_app  # noqa: E402

app.add_typer(manage_app, name="manage", help="Manage provider permissions.")
from tum_mcp.study_cli import app as study_app  # noqa: E402

app.add_typer(study_app, name="study", help="Prepare, preview and publish a course app.")
from tum_mcp.lecture_cli import app as lecture_app  # noqa: E402

app.add_typer(
    lecture_app,
    name="lecture",
    help="Prepare recording evidence with the optional Lecture extension.",
)
from tum_mcp.video_cli import app as video_app  # noqa: E402

app.add_typer(
    video_app,
    name="video-notes",
    help="Render and maintain videos with the optional Video Notes extension.",
)


@app.command()
def version() -> None:
    """Show the campus integration version."""
    typer.echo(__version__)


@app.command()
def serve() -> None:
    """Run the combined campus/Moodle MCP server over stdio."""
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
    """Choose services and complete sign-in."""
    from rich.text import Text

    from tum_mcp.connect import ConnectionResult, ServiceChoice, connect_services
    from tum_mcp.moodle.browsers import discover_browsers
    from tum_mcp.ui import heading, select_browser, select_services, terminal_console

    console = terminal_console()
    if not sys.stdin.isatty():
        raise CampusError(Code.ACTION_REQUIRED, "Run tum-mcp login in your interactive terminal.")
    heading(console, "Login", "Choose services to sign in to. Only selected providers will open.")
    try:
        selected = select_services()
        if not selected:
            console.print("No services selected. Nothing was changed.")
            return
        if ServiceChoice.TUMONLINE in selected:
            console.print(
                "TUMonline defaults to study names, public courses and curriculum positions. "
                "Grades and progress, exams and fee status stay off until you allow them."
            )
            console.print(
                "All MCP clients sharing this configuration use the same permission; "
                "manage it with tum-mcp manage tumonline."
            )
        browser = select_browser(discover_browsers())
    except (KeyboardInterrupt, EOFError):
        console.print("Cancelled. No browser was opened.")
        raise typer.Exit(130) from None
    console.print(Text(f"Browser: {browser.label}"))
    console.print(Text("Opening " + ", ".join(value.label for value in selected) + "."))
    console.print("Complete TUM sign-in/MFA in the browser window.")
    if browser.windows_host:
        console.print("Preparing the private Windows browser driver on first use.")
        console.print("Sessions stay encrypted in WSL; no browser debugging port is opened.")
    console.print("Campus sessions are encrypted locally with an owner-restricted key file.")
    console.print()

    def connected(result: ConnectionResult) -> None:
        console.print(
            Text.assemble(("● ", "ready"), (f"Connected  {result.service.label}", "bold"))
        )
        if result.account is not None:
            console.print(Text(f"Account ID: {result.account.id}"))

    try:
        results = connect_services(selected, on_connected=connected, browser=browser)
    except KeyboardInterrupt:
        console.print("Cancelled. Completed connections were saved.")
        raise typer.Exit(130) from None
    console.print()
    if results:
        console.print(
            f"Saved {len(results)} campus connection(s). "
            "Read access also depends on local settings."
        )
    console.print("Your agent can discover courses and channels, then read the relevant material.")


app.command("connect", hidden=True)(connect)


app.command()(discover)


@app.command()
def logout(provider: Provider, account_id: str) -> None:
    """Remove one local credential; preserve settings, downloads, and workspaces."""
    Vault().logout(find_account(account_id, provider))
    typer.echo("Local credential removed. Revoke remote API keys separately if needed.")


@app.command()
def doctor(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable diagnostics.")
    ] = False,
    live: Annotated[
        bool,
        typer.Option(
            "--live", help="Verify saved campus sessions and optional GitHub authentication."
        ),
    ] = False,
) -> None:
    """Show connections, extensions and relevant client/runtime health."""
    from rich.text import Text

    from tum_mcp.diagnostics import collect_diagnostics
    from tum_mcp.ui import heading, section, status_rows, terminal_console

    report = collect_diagnostics(live=live)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return
    console = terminal_console()
    heading(
        console,
        "Doctor",
        "Local readiness checks"
        + (" and requested live authentication." if live else ". No login or Keychain access."),
    )
    for title, items in (
        ("Services", report.services),
        ("Extensions", report.extensions),
        ("Clients", report.clients),
        ("Runtime", report.runtime),
    ):
        if items:
            section(console, title)
            status_rows(console, [(item.label, item.state, item.detail) for item in items])
    if report.next_steps:
        section(console, "Next steps")
        for index, action in enumerate(report.next_steps, 1):
            console.print(Text(f"{index}. {action}"))
        console.print()
    console.print(
        Text("Campus websites are read-only. Study publication is optional.", style="muted")
    )
    console.print(
        Text("Use --live for a fresh session check; --json for automation.", style="muted")
    )


from tum_mcp.lifecycle_cli import install, setup, uninstall, update  # noqa: E402

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
    """Inspect bundled skills and customization paths."""
    from tum_mcp.skills import inspect_skills

    skills = inspect_skills()
    if json_output:
        typer.echo(json.dumps(skills, indent=2))
        return
    from tum_mcp.ui import State, heading, status_rows, terminal_console

    console = terminal_console()
    heading(console, "Skills", "Active workflow definitions for your configured clients.")
    status_rows(
        console,
        [
            (
                item["name"],
                State.ENABLED,
                "Personal customization." if item["customized"] else "Bundled workflow.",
            )
            for item in skills
        ],
    )
    console.print("Use skills inspect NAME to read a workflow, or --json for metadata.")


@skills_app.command()
def customize(name: str) -> None:
    """Create a personal editable copy without changing its installed counterpart."""
    from tum_mcp.skills import customize_skill

    typer.echo(str(customize_skill(name)))


@skills_app.command("export")
def export_skills(destination: Path) -> None:
    """Export the selected skill pack to a new folder for manual installation/review."""
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
    """Check metadata and real tool references; does not claim routing accuracy."""
    from tum_mcp.skill_validation import validate_skills

    report = validate_skills(include_optional=all_skills)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        from tum_mcp.ui import State, heading, status_rows, terminal_console

        console = terminal_console()
        heading(
            console,
            "Validate skills",
            "Check definitions and tool references; no agent or campus calls.",
        )
        status_rows(
            console,
            [
                (
                    "Workflow definitions",
                    State.FAILED if report.errors else State.READY,
                    f"{len(report.checked_skills)} checked; {len(report.errors)} error(s).",
                )
            ],
        )
        for error in report.errors:
            console.print(str(error), markup=False)
    if report.errors:
        raise typer.Exit(1)


@skills_app.command("inspect")
def inspect_skill(name: str) -> None:
    """Print the selected version of one bundled/customized skill."""
    from tum_mcp.skills import selected

    typer.echo((selected(name) / "SKILL.md").read_text(encoding="utf-8"))


@skills_app.command("diff")
def diff_skill(name: str) -> None:
    """Review the entry-text difference between a personal override and this bundle."""
    from tum_mcp.skills import skill_diff

    typer.echo(skill_diff(name) or "No entry-text difference from the bundled skill.")


@skills_app.command("evaluate")
def evaluate_skills(trials: Path) -> None:
    """Score supplied fresh-session trial records; never invokes another coding agent."""
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
    except (CampusError, MoodleError, BrowserSetupError) as error:
        typer.echo(str(error), err=True)
        raise SystemExit(2) from None
    except OSError as error:
        reason = error.strerror or type(error).__name__
        where = f" ({error.filename})" if error.filename else ""
        typer.echo(
            f"Local files could not be accessed: {reason}{where}. Check permissions and retry.",
            err=True,
        )
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        typer.echo("Cancelled. Completed changes were preserved.", err=True)
        raise SystemExit(130) from None
