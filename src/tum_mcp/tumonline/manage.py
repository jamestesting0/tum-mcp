"""Local TUMonline permission controls and capability status."""

import json
import os
import sys
from typing import Annotated, Final

import questionary
import typer
from prompt_toolkit.output import ColorDepth

from tum_mcp.commands.terminal_input import numbered_input, with_escape
from tum_mcp.commands.ui import (
    MULTI_HINT,
    State,
    fit,
    heading,
    hint,
    selector_style,
    status_rows,
    terminal_console,
)
from tum_mcp.errors import CampusError, Code
from tum_mcp.tumonline.policy import LABELS, PolicyStore, Scope

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
        "Semester fee",
        "Current semester fee invoice, payment deadline and bookings.",
    ),
)


def interactive_terminal() -> bool:
    return sys.stdin.isatty()


def choose_scopes(current: frozenset[Scope]) -> frozenset[Scope] | None:
    console = terminal_console()
    if os.environ.get("TERM") == "dumb":
        console.print("What may your agent read from TUMonline?")
        for index, (scope, label, detail) in enumerate(CATEGORIES, 1):
            state = "on" if scope in current else "off"
            console.print(f"{index}. {label} ({state}): {detail}", markup=False)
        console.print(
            "Enter the numbers to allow, separated by commas, or none · "
            "Enter keeps the current choice · Esc cancels"
        )
        numbers = {str(index): scope for index, (scope, _, _) in enumerate(CATEGORIES, 1)}
        while True:
            answer = numbered_input("Permissions: ").strip().lower()
            if not answer:
                return current
            if answer == "none":
                return frozenset()
            chosen = [part.strip() for part in answer.split(",")]
            if all(part in numbers for part in chosen):
                return frozenset(numbers[part] for part in chosen)
            console.print("Choose numbers from the list, none, or Enter.")

    hint(console, MULTI_HINT.replace("confirm", "save"))
    wide = console.width >= 70
    selected = with_escape(
        questionary.checkbox(
            "What may your agent read from TUMonline?",
            choices=[
                questionary.Choice(
                    [("", f"{label:<21}"), ("class:muted", fit(detail, console, 21))]
                    if wide
                    else [("", label)],
                    value=scope.value,
                    checked=scope in current,
                )
                for scope, label, detail in CATEGORIES
            ],
            qmark="",
            pointer=">",
            style=selector_style(),
            instruction="",
            color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
        )
    ).unsafe_ask()
    return None if selected is None else frozenset(Scope(value) for value in selected)


@app.command("tumonline")
def tumonline(
    account: Annotated[
        str | None,
        typer.Option(
            "--account",
            metavar="ID",
            help="Needed only when several TUMonline accounts are saved.",
            show_default=False,
        ),
    ] = None,
    show: Annotated[bool, typer.Option("--show", help="Show configured permissions.")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable permissions without editing.")
    ] = False,
    disconnect: Annotated[bool, typer.Option("--disconnect", hidden=True)] = False,
) -> None:
    """Choose what your agent may read from TUMonline."""
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
        typer.echo("Removed TUMonline from this computer. Website sessions are not revoked.")
        return
    accounts = store.accounts()
    console = terminal_console()
    if not json_output:
        heading(console, "TUMonline permissions")
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
                        "Run tum-mcp login and choose TUMonline.",
                    )
                ],
            )
        return
    if account is None:
        if len(accounts) != 1:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Several TUMonline accounts are saved; add --account with one of: "
                + ", ".join(accounts)
                + ".",
            )
        account = accounts[0]
    policy = store.read(account)
    if disconnect:
        from tum_mcp.tumonline.identity import AccountRef
        from tum_mcp.tumonline.onboarding import disconnect as remove_session

        remove_session(AccountRef(account_id=account))
        typer.echo("Removed TUMonline from this computer. Website sessions are not revoked.")
        return
    if len(accounts) > 1:
        hint(console, f"Account {account}")
    scope_note = (
        "Applies to every coding app on this computer; "
        "it does not limit other services or programs."
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
        hint(console, scope_note)
        hint(console, "Change them with tum-mcp manage tumonline")
        return
    if not interactive_terminal():
        raise CampusError(Code.ACTION_REQUIRED, "Run this command in an interactive terminal.")
    hint(console, scope_note)
    console.print()
    try:
        selected = choose_scopes(policy.allowed)
    except (EOFError, KeyboardInterrupt):
        selected = None
    if selected is None:
        typer.echo("Cancelled. Permissions were not changed.")
        return
    store.save_scopes(policy, selected)
    allowed = [label for scope, label, _ in CATEGORIES if scope in selected]
    typer.echo("Saved. Allowed: " + (", ".join(allowed) if allowed else "nothing") + ".")
