"""Trusted local setup, update and removal commands."""

import json
import os
import sys
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp.client_hosts import ClientHost
from tum_mcp.errors import CampusError, Code
from tum_mcp.extension_management import ExtensionName


def install(
    extensions: Annotated[
        list[ExtensionName] | None,
        typer.Argument(help="Optional workflows; omit to choose interactively."),
    ] = None,
    asr: Annotated[
        bool, typer.Option(help="Provision optional lecture recognition; models load on demand.")
    ] = True,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable installation results; requires names."),
    ] = False,
) -> None:
    """Choose optional workflows to install, or provide their names."""
    from tum_mcp.extension_management import LABELS, choose_extensions
    from tum_mcp.extensions import install_lecture, set_audio_notes, set_video_notes
    from tum_mcp.ui import State, heading, status_rows, terminal_console

    selected = (
        tuple(extensions)
        if extensions
        else choose_extensions(installing=True, json_output=json_output)
    )
    if not selected:
        return
    console = terminal_console()
    if not json_output and extensions:
        heading(console, "Install", "Add optional workflows to your configured clients.")
    reports = []
    needs_review = False
    for name in dict.fromkeys(selected):
        match name:
            case ExtensionName.LECTURE:
                report = install_lecture(asr=asr)
                review = bool(report["clients"]["needs_review"])
            case ExtensionName.AUDIO_NOTES:
                report = {"extension": name, "state": set_audio_notes(True)}
                review = False
            case ExtensionName.VIDEO_NOTES:
                report = {"extension": name, "state": set_video_notes(True)}
                review = False
            case unreachable:
                assert_never(unreachable)
        reports.append(report)
        needs_review |= review
        if not json_output:
            status_rows(
                console,
                [
                    (
                        LABELS[name],
                        State.ACTION if review else State.ENABLED,
                        "Installed; customized client files need review."
                        if review
                        else "Workflow and tools installed.",
                    )
                ],
            )
    if json_output:
        typer.echo(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2))
    else:
        local = {ExtensionName.AUDIO_NOTES, ExtensionName.VIDEO_NOTES}
        if any(name not in local for name in selected):
            console.print("Use tum-mcp login to sign in to the selected services.")
        else:
            console.print(
                "Audio and Video Notes use your prepared Study content; "
                "no campus connection is needed."
            )
        if ExtensionName.VIDEO_NOTES in selected:
            console.print(
                "The video render runtime installs when first used; "
                "check it with tum-mcp video-notes runtime status."
            )
        console.print("Reload or restart configured clients to load the workflows.")
        if ExtensionName.LECTURE in selected and not asr:
            console.print(
                "Lecture uses captions or imported transcripts; "
                "local recognition was not installed."
            )
    if needs_review:
        raise typer.Exit(2)


def setup(
    client: Annotated[list[str] | None, typer.Option()] = None,
    host: Annotated[
        ClientHost,
        typer.Option(help="Client location; windows registers a Windows client from WSL."),
    ] = ClientHost.LOCAL,
    runtime_only: Annotated[bool, typer.Option("--runtime-only", hidden=True)] = False,
) -> None:
    """Prepare the runtime and choose coding clients to configure."""
    from tum_mcp.client_hosts import client_home
    from tum_mcp.clients import install_client
    from tum_mcp.diagnostics import available_client_checks
    from tum_mcp.ui import State, heading, select_many, status_rows, terminal_console

    prepare_only = runtime_only or (
        not client and not sys.stdin.isatty() and os.environ.get("TUM_MCP_NPM_LAUNCHER") == "1"
    )
    if prepare_only:
        if client:
            raise CampusError(Code.ACTION_REQUIRED, "Choose runtime preparation or client setup.")
        typer.echo("Runtime ready. Run tum-mcp setup interactively to choose coding clients.")
        return
    console = terminal_console()
    heading(console, "Setup", "Choose coding clients to configure or refresh.")
    selected = tuple(client or ())
    if not selected:
        if not sys.stdin.isatty():
            raise CampusError(Code.ACTION_REQUIRED, "Run setup interactively or use --client NAME.")
        checks = available_client_checks(home=client_home(host), host=host, include_generic=True)
        if all(check.state == State.FAILED for _, check in checks):
            status_rows(console, [(check.label, check.state, check.detail) for _, check in checks])
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Review the failed client registrations locally."
            )
        try:
            selected = (
                select_many(
                    "Set up clients",
                    tuple(
                        (name, check.label, check.state, check.state != State.FAILED)
                        for name, check in checks
                    ),
                )
                or ()
            )
        except (EOFError, KeyboardInterrupt):
            selected = ()
        if not selected:
            console.print("Cancelled. Client registrations were not changed.")
            raise typer.Exit(130)
    for name in selected:
        install_client(name, host=host, announce=False)
        status_rows(
            console,
            [
                (
                    name.title(),
                    State.UPDATED,
                    "Managed registration saved; reload or restart the client.",
                )
            ],
        )
    typer.echo("Runtime ready. Run tum-mcp login to sign in to the services you select.")
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
    extensions: Annotated[
        list[ExtensionName] | None,
        typer.Argument(help="Optional workflows; omit to open the picker."),
    ] = None,
    client: Literal["codex", "claude", "cursor", "antigravity", "generic"] | None = None,
    host: ClientHost = ClientHost.LOCAL,
    all_clients: Annotated[bool, typer.Option("--all", hidden=True)] = False,
    purge_runtime: Annotated[
        bool,
        typer.Option(
            help="Remove verified runtimes after this process exits. Close coding clients first."
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable extension results.")
    ] = False,
    forget_credentials: Annotated[
        bool,
        typer.Option(
            help="Also forget local service credentials and Git tokens; keep native-store records."
        ),
    ] = False,
) -> None:
    """Remove managed client files; preserve personal work and saved data by default."""

    if extensions:
        if client or all_clients or purge_runtime or forget_credentials or host != ClientHost.LOCAL:
            raise CampusError(
                Code.SCOPE_DENIED,
                "Extension-only removal cannot use package/client/data cleanup options.",
            )
        from tum_mcp.extension_management import remove_extensions

        remove_extensions(tuple(extensions), json_output=json_output)
        return

    if not client and not all_clients and host == ClientHost.LOCAL:
        from tum_mcp.extension_management import choose_extensions, remove_extensions

        selected = choose_extensions(
            installing=False, json_output=json_output, full_only=purge_runtime or forget_credentials
        )
        if selected:
            remove_extensions(selected, show_heading=False)
        return
    if json_output:
        raise CampusError(
            Code.ACTION_REQUIRED, "--json is supported for named extension removal only."
        )

    if (client is None) == (not all_clients):
        raise CampusError(Code.ACTION_REQUIRED, "Choose --client NAME or use the uninstall picker.")
    if (purge_runtime or forget_credentials) and not all_clients:
        raise CampusError(Code.ACTION_REQUIRED, "Choose All for runtime or credential cleanup.")
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
