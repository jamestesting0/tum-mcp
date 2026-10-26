"""Trusted local setup, update and removal commands."""

import json
import os
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp.client_hosts import ClientHost
from tum_mcp.errors import CampusError, Code


def install(
    extension: Annotated[Literal["lecture", "studocu"], typer.Argument()],
    asr: Annotated[
        bool,
        typer.Option(
            help="Provision the isolated recognizer on supported hosts; models load when needed."
        ),
    ] = True,
) -> None:
    """Install an optional Lecture or Studocu extension."""
    if extension == "studocu":
        from tum_mcp.extensions import set_studocu

        typer.echo(json.dumps({"extension": extension, "state": set_studocu(True)}))
        return
    from tum_mcp.extensions import install_lecture

    report = install_lecture(asr=asr)
    typer.echo(json.dumps(report, indent=2))
    if report["clients"]["needs_review"]:
        raise typer.Exit(2)


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
    typer.echo("Runtime ready. Run tum-mcp connect to sign in to the services you select.")
    if not client:
        typer.echo("Select adapters with --client codex, claude, cursor, antigravity, or generic.")
    from tum_mcp.moodle.browsers import is_wsl

    if is_wsl() and host == ClientHost.LOCAL:
        typer.echo("For a Windows desktop client, repeat setup with --host windows.")


def update() -> None:
    """Refresh configured clients after the npm launcher prepares the chosen version."""
    from tum_mcp.extensions import lecture_installation, prepare_recognizer
    from tum_mcp.ui import State, heading, status_rows, terminal_console
    from tum_mcp.updates import refresh_clients

    console = terminal_console()
    heading(console, "Update", "Refresh configured clients for this installed package version.")
    lecture = lecture_installation(strict=True)
    if lecture is not None and lecture.enabled:
        prepare_recognizer(lecture.asr_requested)
    report = refresh_clients()
    rows = []
    for item in report["clients"]:
        match item["state"]:
            case "updated":
                state = State.UPDATED
            case "needs_review":
                state = State.ACTION
            case "not_registered" | "skipped":
                state = State.INFO
            case unreachable:
                assert_never(unreachable)
        rows.append((f"{item['client'].title()} ({item['host']})", state, item["detail"]))
    if rows:
        status_rows(console, rows)
    console.print(f"Refreshed {report['updated']} client(s); {report['needs_review']} need review.")
    console.print("Sessions, preferences, downloads and previous runtimes are retained.")
    if report["needs_review"]:
        raise typer.Exit(2)


def uninstall(
    extension: Annotated[Literal["lecture", "studocu"] | None, typer.Argument()] = None,
    client: Literal["codex", "claude", "cursor", "antigravity", "generic"] | None = None,
    host: ClientHost = ClientHost.LOCAL,
    all_clients: Annotated[
        bool, typer.Option("--all", help="Remove managed registrations for all configured clients.")
    ] = False,
    purge_runtime: Annotated[
        bool,
        typer.Option(
            help="Remove verified runtimes after this process exits. Close coding clients first."
        ),
    ] = False,
    forget_credentials: Annotated[
        bool,
        typer.Option(
            help="Also forget local service credentials and Git tokens; keep native-store records."
        ),
    ] = False,
) -> None:
    """Remove managed client files; preserve personal work and saved data by default."""

    if extension is not None:
        if client or all_clients or purge_runtime or forget_credentials or host != ClientHost.LOCAL:
            raise CampusError(
                Code.SCOPE_DENIED,
                "Extension-only removal cannot use package/client/data cleanup options.",
            )
        if extension == "studocu":
            from tum_mcp.extensions import set_studocu

            state = set_studocu(False)
            typer.echo(json.dumps({"extension": extension, "state": state}))
            if state == "disabled_needs_review":
                raise typer.Exit(2)
            return
        from tum_mcp.extensions import uninstall_lecture

        report = uninstall_lecture()
        typer.echo(json.dumps(report, indent=2))
        if report["clients"]["needs_review"]:
            raise typer.Exit(2)
        return

    if (client is None) == (not all_clients):
        raise CampusError(Code.ACTION_REQUIRED, "Choose --client NAME or --all.")
    if (purge_runtime or forget_credentials) and not all_clients:
        raise CampusError(Code.ACTION_REQUIRED, "Runtime/credential cleanup requires --all.")
    if purge_runtime and os.environ.get("TUM_MCP_NPM_LAUNCHER") != "1":
        raise CampusError(Code.ACTION_REQUIRED, "Use the npm tum-mcp launcher for runtime cleanup.")
    if all_clients:
        from tum_mcp.removal import remove_clients

        remove_clients(purge_runtime=purge_runtime, forget_credentials=forget_credentials)
    else:
        from tum_mcp.uninstall import uninstall_client

        if client is None:
            raise CampusError(Code.ACTION_REQUIRED, "Choose a client.")
        uninstall_client(client, host=host)
