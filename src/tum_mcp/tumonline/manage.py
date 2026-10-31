"""Local TUMonline permission controls and capability status."""

import json
import os
import sys
from typing import Annotated, Final

import questionary
import typer
from prompt_toolkit.output import ColorDepth

from tum_mcp.errors import CampusError, Code
from tum_mcp.tumonline.policy import LABELS, PolicyStore, Scope
from tum_mcp.ui import (
    State,
    heading,
    selection_label,
    selector_style,
    status_rows,
    terminal_console,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
CATEGORIES: Final = (
    (
        Scope.STUDIES_COURSES,
        LABELS[Scope.STUDIES_COURSES],
        "Study names, public courses and course curriculum positions.",
    ),
    (
        Scope.ACADEMIC_PROGRESS,
        LABELS[Scope.ACADEMIC_PROGRESS],
        "Your achievements with grades and credits, and progress per study.",
    ),
    (
        Scope.EXAMS,
        LABELS[Scope.EXAMS],
        "Registered exams and exam offers with dates, rooms and registration windows.",
    ),
    (
        Scope.ADMISSION,
        LABELS[Scope.ADMISSION],
        "Current semester fee invoice, payment deadline and bookings.",
    ),
)


def interactive_terminal() -> bool:
    return sys.stdin.isatty()


def choose_scopes(current: frozenset[Scope]) -> frozenset[Scope] | None:
    console = terminal_console()
    if os.environ.get("TERM") == "dumb":
        console.print("TUMonline permissions")
        for index, (scope, label, _) in enumerate(CATEGORIES, 1):
            console.print(f"{index}. {label} ({'allowed' if scope in current else 'denied'})")
        console.print(
            "Enter the numbers to allow, separated by commas, none to deny all, "
            "or press Enter to keep the current settings."
        )
        numbers = {str(index): scope for index, (scope, _, _) in enumerate(CATEGORIES, 1)}
        while True:
            answer = console.input("Permissions: ").strip().lower()
            if not answer:
                return current
            if answer == "none":
                return frozenset()
            chosen = [part.strip() for part in answer.split(",")]
            if all(part in numbers for part in chosen):
                return frozenset(numbers[part] for part in chosen)
            console.print("Choose numbers from the list, none, or Enter.")

    console.print("Up/down: move · Space: select")
    console.print("Enter: save · Ctrl+C: cancel")
    console.print()
    selected = questionary.checkbox(
        "TUMonline permissions",
        choices=[
            questionary.Choice(
                selection_label(label, State.ENABLED if scope in current else State.DISABLED),
                value=scope.value,
                checked=scope in current,
            )
            for scope, label, _ in CATEGORIES
        ],
        qmark="",
        pointer=">",
        style=selector_style(),
        instruction="",
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
    ).unsafe_ask()
    return None if selected is None else frozenset(Scope(value) for value in selected)


@app.command("tumonline")
def tumonline(
    account: Annotated[str | None, typer.Option("--account")] = None,
    show: Annotated[bool, typer.Option("--show", help="Show configured permissions.")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable permissions without editing.")
    ] = False,
    disconnect: Annotated[
        bool, typer.Option("--disconnect", help="Remove the local session.")
    ] = False,
) -> None:
    """Inspect TUMonline permissions and implementation availability."""
    store = PolicyStore()
    if disconnect and (show or json_output):
        raise CampusError(Code.ACTION_REQUIRED, "Choose --show or --disconnect, not both.")
    if disconnect and account is not None:
        from pydantic import ValidationError

        from tum_mcp.tumonline.identity import AccountRef
        from tum_mcp.tumonline.onboarding import disconnect as remove_session

        try:
            target = AccountRef(account_id=account)
        except ValidationError:
            raise CampusError(Code.SCOPE_DENIED, "Invalid TUMonline account identifier.") from None
        remove_session(target)
        typer.echo("Local TUMonline session removed. Remote sessions are not revoked.")
        return
    accounts = store.accounts()
    console = terminal_console()
    if not json_output:
        heading(
            console,
            "TUMonline permissions",
            "Control the TUMonline reads available to your coding clients.",
        )
    if not accounts:
        if json_output:
            typer.echo(json.dumps({"accounts": []}))
        else:
            status_rows(
                console,
                [
                    (
                        "TUMonline",
                        State.UNCONFIGURED,
                        "No TUMonline policy is configured. Run tum-mcp login to sign in.",
                    )
                ],
            )
        return
    if account is None:
        if len(accounts) != 1:
            raise CampusError(Code.ACTION_REQUIRED, "Choose an account with --account.")
        account = accounts[0]
    policy = store.read(account)
    if disconnect:
        from tum_mcp.tumonline.identity import AccountRef
        from tum_mcp.tumonline.onboarding import disconnect as remove_session

        remove_session(AccountRef(account_id=account))
        typer.echo("Local TUMonline session removed. Remote sessions are not revoked.")
        return
    context = (
        f"Policy account: {account}",
        "These permissions apply to all MCP clients sharing this configuration.",
        "Other providers and local programs are outside this policy's control.",
    )
    if show or json_output:
        if json_output:
            typer.echo(policy.model_dump_json(indent=2))
            return
        status_rows(
            console,
            [
                (label, State.ENABLED if policy.allows(scope) else State.DISABLED, detail)
                for scope, label, detail in CATEGORIES
            ],
        )
        console.print("Edit permissions: tum-mcp manage tumonline", markup=False)
        console.print(context[1], markup=False)
        console.print(context[2], markup=False)
        return
    if not interactive_terminal():
        raise CampusError(Code.ACTION_REQUIRED, "Run this command in an interactive terminal.")
    console = terminal_console()
    for line in context[1:]:
        console.print(line, markup=False)
    for _, label, detail in CATEGORIES:
        console.print(f"{label}: {detail}", markup=False)
    try:
        selected = choose_scopes(policy.allowed)
    except (EOFError, KeyboardInterrupt):
        selected = None
    if selected is None:
        typer.echo("Cancelled. Permissions were not changed.")
        return
    store.save_scopes(policy, selected)
    typer.echo("Saved.")
