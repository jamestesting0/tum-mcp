"""Local TUMonline permission controls and capability status."""

import json
import os
import sys
from typing import Annotated

import questionary
import typer
from prompt_toolkit.output import ColorDepth

from tum_mcp.errors import CampusError, Code
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.ui import (
    State,
    heading,
    selection_label,
    selector_style,
    status_rows,
    terminal_console,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def interactive_terminal() -> bool:
    return sys.stdin.isatty()


def choose_studies(current: bool) -> bool | None:
    console = terminal_console()
    categories = (
        "Studies and courses",
        "Grades and progress",
        "Exams",
        "Admission",
        "Account",
        "Other IT services",
        "Miscellaneous",
    )
    if os.environ.get("TERM") == "dumb":
        console.print("TUMonline permissions")
        console.print(f"1. {categories[0]} ({'allowed' if current else 'denied'})")
        for category in categories[1:]:
            console.print(f"   {category} (unavailable)")
        console.print("Enter 1 to allow, none to deny, or press Enter to keep the current setting.")
        while True:
            answer = console.input("Permissions: ").strip().lower()
            if answer in {"", "1", "none"}:
                return current if not answer else answer == "1"
            console.print("Choose 1, none, or Enter.")

    console.print("Up/down: move · Space: select")
    console.print("Enter: save · Ctrl+C: cancel")
    console.print()
    selected = questionary.checkbox(
        "TUMonline permissions",
        choices=[
            questionary.Choice(
                selection_label(categories[0], State.ENABLED if current else State.DISABLED),
                value=Scope.STUDIES_COURSES.value,
                checked=current,
            ),
            *[
                questionary.Choice(selection_label(category, State.UNAVAILABLE), disabled=True)
                for category in categories[1:]
            ],
        ],
        qmark="",
        pointer=">",
        style=selector_style(),
        instruction="",
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
    ).unsafe_ask()
    return None if selected is None else Scope.STUDIES_COURSES.value in selected


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
                        "No TUMonline policy is configured. Run tum-mcp connect to sign in.",
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
        labels = (
            "Studies and courses",
            "Grades and progress",
            "Exams",
            "Admission",
            "Account",
            "Other IT services",
            "Miscellaneous",
        )
        rows = []
        for scope, label in zip(Scope, labels, strict=True):
            if scope == Scope.STUDIES_COURSES:
                rows.append(
                    (
                        label,
                        State.ENABLED if policy.allows(scope) else State.DISABLED,
                        "Study names, public courses and course curriculum positions.",
                    )
                )
            else:
                rows.append(
                    (label, State.UNAVAILABLE, "Reader not verified; access remains unavailable.")
                )
        status_rows(console, rows)
        console.print("Edit permissions: tum-mcp manage tumonline", markup=False)
        console.print(context[1], markup=False)
        console.print(context[2], markup=False)
        return
    if not interactive_terminal():
        raise CampusError(Code.ACTION_REQUIRED, "Run this command in an interactive terminal.")
    console = terminal_console()
    for line in context[1:]:
        console.print(line, markup=False)
    console.print(
        "Studies and courses includes study names, public courses and curriculum positions."
    )
    if policy.allowed - {Scope.STUDIES_COURSES}:
        console.print("Previously configured unavailable permissions are retained but inactive.")
    try:
        selected = choose_studies(policy.allows(Scope.STUDIES_COURSES))
    except (EOFError, KeyboardInterrupt):
        selected = None
    if selected is None:
        typer.echo("Cancelled. Permissions were not changed.")
        return
    scopes = policy.allowed - {Scope.STUDIES_COURSES}
    if selected:
        scopes |= {Scope.STUDIES_COURSES}
    store.save_scopes(policy, scopes)
    typer.echo("Saved. Unverified readers remain unavailable.")
