"""Trusted local setup, update and removal commands."""

import json
import os
import sys
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp.clients.hosts import ClientHost
from tum_mcp.errors import CampusError, Code
from tum_mcp.extension_management import ExtensionName


def install(
    extensions: Annotated[
        list[ExtensionName] | None,
        typer.Argument(
            metavar="[WORKFLOW]...",
            help="lecture, audio-notes, video-notes or course-memory; omit to choose.",
            show_default=False,
        ),
    ] = None,
    asr: Annotated[
        bool,
        typer.Option(
            help="Install local speech-to-text for lectures without captions; "
            "models download when first used."
        ),
    ] = True,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable installation results; requires names."),
    ] = False,
) -> None:
    """Add optional workflows."""
    from tum_mcp.commands.ui import heading, next_steps, terminal_console
    from tum_mcp.extension_management import choose_extensions

    selected = (
        tuple(extensions)
        if extensions
        else choose_extensions(installing=True, json_output=json_output)
    )
    if not selected:
        return
    console = terminal_console()
    if not json_output and extensions:
        heading(console, "Install")
    reports, needs_review = _install_workflows(selected, asr=asr, json_output=json_output)
    if json_output:
        typer.echo(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2))
    else:
        if ExtensionName.LECTURE in selected and not asr:
            console.print("Lecture will use captions or imported transcripts only.")
        if ExtensionName.VIDEO_NOTES in selected:
            console.print("The video render runtime installs the first time you render.")
        steps = ["Restart your coding apps to load the new workflows."]
        if ExtensionName.LECTURE in selected:
            steps.append("Run tum-mcp login and choose TUM-Live to read lecture recordings.")
        next_steps(console, steps)
    if needs_review:
        raise typer.Exit(2)


def _install_workflows(
    selected: tuple[ExtensionName, ...], *, asr: bool, json_output: bool
) -> tuple[list[object], bool]:
    """Install each workflow and show its row; True when client files need review."""
    from tum_mcp.commands.ui import State, status_rows, terminal_console
    from tum_mcp.extension_management import LABELS
    from tum_mcp.extensions import (
        install_lecture,
        set_audio_notes,
        set_course_memory,
        set_video_notes,
    )

    console = terminal_console()
    reports = []
    rows: list[tuple[str, State, str]] = []
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
            case ExtensionName.COURSE_MEMORY:
                report = {"extension": name, "state": set_course_memory(True)}
                review = False
            case unreachable:
                assert_never(unreachable)
        reports.append(report)
        needs_review |= review
        rows.append(
            (
                LABELS[name],
                State.ACTION if review else State.ENABLED,
                "Installed; customized coding-app files need review." if review else "Installed.",
            )
        )
    if rows and not json_output:
        status_rows(console, rows)
    return reports, needs_review


def setup(
    client: Annotated[
        list[str] | None,
        typer.Option(
            metavar="NAME",
            help="codex, claude, cursor, antigravity or generic (writes mcp.json); repeatable.",
            show_default=False,
        ),
    ] = None,
    host: Annotated[
        ClientHost,
        typer.Option(help="Use windows to set up a Windows coding app from WSL."),
    ] = ClientHost.LOCAL,
    runtime_only: Annotated[bool, typer.Option("--runtime-only", hidden=True)] = False,
) -> None:
    """Connect TUM MCP to your coding apps and choose optional workflows."""
    from tum_mcp.clients import install_client
    from tum_mcp.clients.hosts import client_home
    from tum_mcp.commands.ui import (
        State,
        client_label,
        fit,
        heading,
        next_steps,
        select_many,
        status_rows,
        terminal_console,
    )
    from tum_mcp.diagnostics import available_client_checks

    prepare_only = runtime_only or (
        not client and not sys.stdin.isatty() and os.environ.get("TUM_MCP_NPM_LAUNCHER") == "1"
    )
    if prepare_only:
        if client:
            raise CampusError(Code.ACTION_REQUIRED, "Choose runtime preparation or client setup.")
        typer.echo("Runtime ready. Run tum-mcp setup interactively to choose coding clients.")
        return
    console = terminal_console()
    heading(
        console,
        "Setup",
        "Adds TUM tools, skills and a course completion hook to the apps you choose. "
        "Their other settings stay as they are.",
    )
    selected = tuple(client or ())
    if not selected:
        if not sys.stdin.isatty():
            raise CampusError(Code.ACTION_REQUIRED, "Run setup interactively or use --client NAME.")
        checks = available_client_checks(home=client_home(host), host=host, include_generic=True)
        if all(check.state == State.FAILED for _, check in checks):
            status_rows(console, [(check.label, check.state, check.detail) for _, check in checks])
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Every coding-app registration failed its check; see the details above.",
            )
        if all(name == "generic" for name, _ in checks):
            # Generic alone is a manual export, not a client the student already uses.
            console.print(
                "No supported coding app was found. Install Codex, Claude Code, Cursor or "
                "Antigravity and run setup again, or use tum-mcp setup --client generic."
            )
        else:
            try:
                picked = select_many(
                    "Which coding apps should use TUM MCP?",
                    tuple(
                        (
                            name,
                            client_label(name),
                            "not set up" if check.state == State.UNCONFIGURED else "set up",
                            check.state != State.FAILED or "needs review",
                        )
                        for name, check in checks
                    ),
                    optional=True,
                )
            except (EOFError, KeyboardInterrupt):
                picked = None
            if picked is None:
                console.print("Cancelled. Nothing was changed.")
                raise typer.Exit(130)
            selected = picked
    results = [
        (client_label(name, host.value), *install_client(name, host=host, announce=False))
        for name in selected
    ]
    if results:
        console.print()
        status_rows(console, results)
    needs_review = False
    if not client:
        # First-time setup ends in one command: offer the optional workflows here too.
        from tum_mcp.extension_management import extension_rows

        wide = console.width >= 70
        choices = tuple(
            (
                name,
                f"{label:<14} {fit(description, console, 14)}"
                if wide and state == State.DISABLED
                else label,
                None,
                state == State.DISABLED or "installed",
            )
            for name, label, state, description, _ in extension_rows()
        )
        if any(selectable is True for *_, selectable in choices):
            try:
                workflows = (
                    select_many("Add optional workflows? (Enter skips)", choices, optional=True)
                    or ()
                )
            except (EOFError, KeyboardInterrupt):
                workflows = ()
            _, needs_review = _install_workflows(workflows, asr=True, json_output=False)
    if not selected:
        console.print("No coding app was set up.")
    steps = []
    if selected:
        names = ", ".join(client_label(name) for name in selected)
        steps.append(f"Restart {names} and open a new chat.")
    steps.append("Run tum-mcp login to sign in to campus services.")
    from tum_mcp.moodle.browsers import is_wsl

    if is_wsl() and host == ClientHost.LOCAL:
        steps.append("To use a Windows coding app too, run tum-mcp setup --host windows.")
    console.print()
    next_steps(console, steps)
    if needs_review:
        raise typer.Exit(2)


def update() -> None:
    """Update TUM MCP and refresh your coding apps."""
    from tum_mcp.commands.ui import (
        State,
        client_label,
        count,
        heading,
        status_rows,
        terminal_console,
    )
    from tum_mcp.extensions import lecture_installation, prepare_recognizer
    from tum_mcp.updates import refresh_clients

    console = terminal_console()
    heading(console, "Update", version=True)
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
        rows.append((client_label(item["client"], item["host"]), state, item["detail"]))
    if rows:
        status_rows(console, rows)
    refreshed = [
        client_label(item["client"], item["host"])
        for item in report["clients"]
        if item["state"] == "updated"
    ]
    if refreshed:
        console.print(f"Restart {', '.join(refreshed)} to load the update.")
    elif not rows:
        console.print("No coding app is set up yet. Run tum-mcp setup.")
    if report["needs_review"]:
        console.print(f"{count(report['needs_review'], 'app needs', 'apps need')} review.")
    if report["needs_review"]:
        raise typer.Exit(2)


def uninstall(
    extensions: Annotated[
        list[ExtensionName] | None,
        typer.Argument(
            metavar="[WORKFLOW]...",
            help="lecture, audio-notes, video-notes or course-memory; omit to choose.",
            show_default=False,
        ),
    ] = None,
    client: Annotated[
        Literal["codex", "claude", "cursor", "antigravity", "generic"] | None,
        typer.Option(
            metavar="NAME",
            help="Remove only this coding app's registration "
            "(codex, claude, cursor, antigravity or generic).",
            show_default=False,
        ),
    ] = None,
    host: Annotated[
        ClientHost, typer.Option(help="Use windows for a Windows coding app set up from WSL.")
    ] = ClientHost.LOCAL,
    all_clients: Annotated[bool, typer.Option("--all", hidden=True)] = False,
    purge_runtime: Annotated[
        bool,
        typer.Option(
            help="With Everything: also remove downloaded runtimes. Close coding apps first."
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable extension results.")
    ] = False,
    forget_credentials: Annotated[
        bool,
        typer.Option(
            help="With Everything: also forget saved campus sign-ins and Git tokens "
            "(system credential store entries stay)."
        ),
    ] = False,
) -> None:
    """Remove workflows, a coding-app registration, or TUM MCP itself."""

    if extensions:
        if client or all_clients or purge_runtime or forget_credentials or host != ClientHost.LOCAL:
            raise CampusError(
                Code.SCOPE_DENIED,
                "Workflow removal cannot be combined with --client, --host, "
                "--purge-runtime or --forget-credentials.",
            )
        from tum_mcp.extension_management import remove_extensions

        remove_extensions(tuple(extensions), json_output=json_output)
        return

    if not client and not all_clients and host == ClientHost.LOCAL:
        from tum_mcp.extension_management import choose_extensions, remove_extensions

        selected = choose_extensions(
            installing=False,
            json_output=json_output,
            purge=purge_runtime,
            forget=forget_credentials,
        )
        if selected:
            remove_extensions(selected, show_heading=False)
        return
    if json_output:
        raise CampusError(
            Code.ACTION_REQUIRED, "--json is supported for named extension removal only."
        )

    if (client is None) == (not all_clients):
        raise CampusError(
            Code.ACTION_REQUIRED, "Name a coding app with --client NAME, or run tum-mcp uninstall."
        )
    if (purge_runtime or forget_credentials) and not all_clients:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "--purge-runtime and --forget-credentials apply only when removing Everything; "
            "run tum-mcp uninstall and choose Everything.",
        )
    if purge_runtime and os.environ.get("TUM_MCP_NPM_LAUNCHER") != "1":
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Runtime cleanup runs through the npm command: run tum-mcp uninstall from npm.",
        )
    if all_clients:
        from tum_mcp.removal import remove_clients

        remove_clients(purge_runtime=purge_runtime, forget_credentials=forget_credentials)
    else:
        from tum_mcp.uninstall import uninstall_client

        if client is None:
            raise CampusError(Code.ACTION_REQUIRED, "Choose a client.")
        uninstall_client(client, host=host)
