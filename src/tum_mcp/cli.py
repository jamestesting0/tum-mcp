"""Local settings and onboarding commands; never runs automatically on npm install."""

import getpass
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Annotated, Literal, assert_never

import typer
from pydantic import SecretStr

from tum_mcp import __version__
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import (
    Provider,
    config_dir,
    data_dir,
    find_account,
    preferences,
    save_account,
)

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
def connect(
    provider: Literal["artemis", "zulip", "campus"],
    auth: Literal["browser", "api-key"] = "browser",
) -> None:
    """Sign in through a temporary browser; campus shares one Artemis/Zulip SSO context."""
    from tum_mcp.connect import connect_browser, connect_zulip

    if not sys.stdin.isatty():
        raise CampusError(Code.ACTION_REQUIRED, "Run connect in your own interactive terminal.")
    if auth == "api-key":
        if provider != "zulip":
            raise CampusError(Code.CAPABILITY_UNSUPPORTED, "API-key import is only for Zulip.")
        typer.echo("Import your existing Zulip API key locally; no password reset is needed.")
        email = typer.prompt("Zulip email")
        key = SecretStr(getpass.getpass("Zulip API key (hidden): "))
        accounts = (connect_zulip(email, key),)
    else:
        providers = (
            (Provider.ARTEMIS, Provider.ZULIP) if provider == "campus" else (Provider(provider),)
        )
        typer.echo("Complete service sign-in in the Chrome tabs. Only own identity is checked.")
        accounts = connect_browser(providers)
    for account in accounts:
        typer.echo(f"Connected {account.provider}. Account ID: {account.id}")
    typer.echo("Existing scopes preserved. New identities have no enabled courses or channels.")


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
def doctor() -> None:
    """Report prerequisites without authenticating or changing client configuration."""
    from tum_mcp.skills import inspect_skills

    typer.echo(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "git": bool(shutil.which("git")),
                "docker_cli": bool(shutil.which("docker")),
                "codex": bool(shutil.which("codex")),
                "claude": bool(shutil.which("claude")),
                "config": str(config_dir()),
                "data": str(data_dir()),
                "bundled_skills": inspect_skills(),
                "live_authentication": "not_checked",
                "client_skill_loading": "not_verified",
                "assignment_test_isolation": "requires_running_engine_and_approved_recipe",
            },
            indent=2,
        )
    )


@app.command()
def setup(client: Annotated[list[str] | None, typer.Option()] = None) -> None:
    """Register explicitly chosen clients; no login or course retrieval occurs."""
    from tum_mcp.clients import install_client

    for name in client or []:
        install_client(name)
    typer.echo("Runtime ready. Complete service connections and select scopes separately.")
    if not client:
        typer.echo("Select adapters with --client codex, --client claude, or --client generic.")


@app.command()
def uninstall(client: Literal["codex", "claude", "generic"]) -> None:
    """Remove an unchanged managed client entry; preserve all campus state and personal work."""
    from tum_mcp.uninstall import uninstall_client

    uninstall_client(client)


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
    try:
        app()
    except CampusError as error:
        typer.echo(str(error), err=True)
        raise SystemExit(2) from None
