"""Local settings and onboarding commands; never runs automatically on npm install."""

import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp import __version__
from tum_mcp.client_hosts import ClientHost
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import (
    Provider,
    find_account,
    preferences,
    save_account,
)
from tum_moodle.browsers import BrowserSetupError
from tum_moodle.errors import MoodleError

app = typer.Typer(no_args_is_help=True)
skills_app = typer.Typer(no_args_is_help=True)
app.add_typer(skills_app, name="skills")
from tum_mcp.workflow_cli import app as workspace_app  # noqa: E402

app.add_typer(workspace_app, name="workspace")
from tum_mcp.action_cli import app as actions_app  # noqa: E402

app.add_typer(actions_app, name="actions")


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
    server.run()


@app.command()
def status() -> None:
    """Show configuration only; does not claim that saved sessions are valid."""
    typer.echo(
        json.dumps(
            {
                "version": __version__,
                "state": "configured_not_live_verified",
                "accounts": [
                    account.model_dump(mode="json") | {"account_id": account.id}
                    for account in preferences().accounts
                ],
                "remote_actions": "disabled",
                "registry": "not_checked",
            },
            indent=2,
        )
    )


@app.command()
def connect() -> None:
    """Select services and a browser, then complete sign-in in its temporary window."""
    from rich.text import Text

    from tum_mcp.connect import ConnectionResult, connect_services
    from tum_mcp.ui import heading, select_browser, select_services, terminal_console
    from tum_moodle.browsers import discover_browsers

    console = terminal_console()
    if not sys.stdin.isatty():
        raise CampusError(Code.ACTION_REQUIRED, "Run tum-mcp connect in your interactive terminal.")
    heading(console, "Connect", "Choose services, then a browser. Only selected tabs will open.")
    try:
        selected = select_services()
        if not selected:
            console.print("No services selected. Nothing was changed.")
            return
        browser = select_browser(discover_browsers())
    except (KeyboardInterrupt, EOFError):
        console.print("Cancelled. No browser was opened.")
        raise typer.Exit(130) from None
    console.print(Text(f"Browser: {browser.label}"))
    console.print(Text("Opening " + ", ".join(value.value.title() for value in selected) + "."))
    console.print("Complete TUM sign-in/MFA in the browser window.")
    if browser.windows_host:
        console.print("Preparing the private Windows browser driver on first use.")
        console.print("Sessions stay encrypted in WSL; no browser debugging port is opened.")
    console.print("Sessions are encrypted locally with an owner-restricted key file.")
    console.print(
        "This avoids Keychain prompts, with less protection than native credential storage."
    )
    console.print()

    def connected(result: ConnectionResult) -> None:
        console.print(
            Text.assemble(("· ", "ready"), (f"Connected  {result.service.value.title()}", "bold"))
        )
        if result.account is not None:
            console.print(Text(f"Account ID: {result.account.id}"))

    try:
        results = connect_services(selected, on_connected=connected, browser=browser)
    except KeyboardInterrupt:
        console.print("Cancelled. Completed connections were saved.")
        raise typer.Exit(130) from None
    console.print()
    console.print(
        f"Saved {len(results)} connection(s). Existing course/channel scopes are preserved."
    )
    console.print("New Artemis/Zulip accounts need scope selection before content reads.")
    console.print("Your coding agent can use status, discover and scope to help with your choices.")


@app.command()
def scope(
    provider: Provider,
    account_id: str,
    channel: Annotated[list[int] | None, typer.Option()] = None,
    private_channel: Annotated[list[int] | None, typer.Option()] = None,
    course: Annotated[list[int] | None, typer.Option()] = None,
    sensitive: Annotated[bool | None, typer.Option("--sensitive/--no-sensitive")] = None,
    workspace: Annotated[bool | None, typer.Option("--workspace/--no-workspace")] = None,
) -> None:
    """Replace explicitly supplied scopes. Only this local command can change grants."""
    from tum_mcp.settings import Account

    current = find_account(account_id, provider)
    values = current.model_dump()
    for key, replacement in (
        ("channels", channel),
        ("private_channels", private_channel),
        ("courses", course),
        ("sensitive_reads", sensitive),
        ("workspace_writes", workspace),
    ):
        if replacement is not None:
            values[key] = replacement
    updated = Account.model_validate(values)
    if not set(updated.private_channels).issubset(updated.channels):
        raise CampusError(
            Code.SCOPE_DENIED, "Private channels must also be in the channel allowlist."
        )
    save_account(updated)
    typer.echo("Scope saved. Remote actions and DMs remain disabled.")


@app.command()
def discover(provider: Provider, account_id: str) -> None:
    """Explicitly discover channel/course metadata for local scope selection."""
    from tum_mcp.artemis import Artemis
    from tum_mcp.transport import API
    from tum_mcp.zulip import Zulip

    api = API(find_account(account_id, provider))
    match provider:
        case Provider.ZULIP:
            typer.echo(Zulip(api).channels().model_dump_json(indent=2))
        case Provider.ARTEMIS:
            typer.echo(Artemis(api).courses().model_dump_json(indent=2))
        case unreachable:
            assert_never(unreachable)


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
        bool, typer.Option("--live", help="Verify saved local sessions with the services.")
    ] = False,
) -> None:
    """Show service readiness, client registrations, prerequisites and useful next actions."""
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
        ("Clients", report.clients),
        ("Runtime", report.runtime),
    ):
        section(console, title)
        status_rows(console, [(item.label, item.state, item.detail) for item in items])
    if report.next_steps:
        section(console, "Next steps")
        for index, action in enumerate(report.next_steps, 1):
            console.print(Text(f"{index}. {action}"))
        console.print()
    console.print(Text("Remote start, push, submit and rebuild remain disabled.", style="muted"))
    console.print(
        Text("Use --live for a fresh session check; --json for automation.", style="muted")
    )


@app.command()
def setup(
    client: Annotated[list[str] | None, typer.Option()] = None,
    host: Annotated[
        ClientHost,
        typer.Option(help="Client location; windows registers a Windows client from WSL."),
    ] = ClientHost.LOCAL,
) -> None:
    """Register explicitly chosen clients; no login or course retrieval occurs."""
    from tum_mcp.clients import install_client

    for name in client or []:
        install_client(name, host=host)
    typer.echo("Runtime ready. Complete service connections and select scopes separately.")
    if not client:
        typer.echo("Select adapters with --client codex, claude, cursor, antigravity, or generic.")
    from tum_moodle.browsers import is_wsl

    if is_wsl() and host == ClientHost.LOCAL:
        typer.echo("For a Windows desktop client, repeat setup with --host windows.")


@app.command()
def uninstall(
    client: Literal["codex", "claude", "cursor", "antigravity", "generic"],
    host: ClientHost = ClientHost.LOCAL,
) -> None:
    """Remove an unchanged managed client entry; preserve all campus state and personal work."""
    from tum_mcp.uninstall import uninstall_client

    uninstall_client(client, host=host)


@skills_app.command("list")
def list_skills() -> None:
    """Inspect bundled skills and customization paths."""
    from tum_mcp.skills import inspect_skills

    typer.echo(json.dumps(inspect_skills(), indent=2))


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
def validate_skill_pack() -> None:
    """Check metadata and real tool references; does not claim routing accuracy."""
    from tum_mcp.skill_validation import validate_skills

    report = validate_skills()
    typer.echo(report.model_dump_json(indent=2))
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


def main() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if isinstance(stream, io.TextIOWrapper):
                stream.reconfigure(encoding="utf-8")
    try:
        app()
    except (CampusError, MoodleError, BrowserSetupError) as error:
        typer.echo(str(error), err=True)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        typer.echo("Connection cancelled. Completed sign-ins were preserved.", err=True)
        raise SystemExit(130) from None
