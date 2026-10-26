"""Local TUMonline permission controls and capability status."""

import os
import sys
from typing import Annotated

import questionary
import typer
from prompt_toolkit.output import ColorDepth

from tum_mcp.errors import CampusError, Code
from tum_mcp.tumonline.policy import PolicyStore, Scope

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def interactive_terminal() -> bool:
    return sys.stdin.isatty()


def choose_studies(current: bool) -> bool | None:
    from tum_mcp.ui import terminal_console

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
    colors = (
        []
        if "NO_COLOR" in os.environ
        else [
            ("pointer", "fg:ansicyan bold"),
            ("highlighted", "bold"),
            ("selected", "noreverse bold"),
            ("instruction", ""),
        ]
    )
    selected = questionary.checkbox(
        "TUMonline permissions",
        choices=[
            questionary.Choice(categories[0], value=Scope.STUDIES_COURSES.value, checked=current),
            *[questionary.Choice(category, disabled="unavailable") for category in categories[1:]],
        ],
        qmark="",
        pointer=">",
        style=questionary.Style(colors),
        instruction="",
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
    ).unsafe_ask()
    return None if selected is None else Scope.STUDIES_COURSES.value in selected


@app.command("tumonline")
def tumonline(
    account: Annotated[str | None, typer.Option("--account")] = None,
    show: Annotated[bool, typer.Option("--show", help="Show configured permissions.")] = False,
    disconnect: Annotated[
        bool, typer.Option("--disconnect", help="Remove the local session.")
    ] = False,
) -> None:
    """Inspect TUMonline permissions and implementation availability."""
    store = PolicyStore()
    if disconnect and show:
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
    if not accounts:
        typer.echo("No TUMonline policy is configured. Run tum-mcp connect to sign in.")
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
    if show:
        for line in context:
            typer.echo(line)
        for scope in Scope:
            configured = "allowed" if policy.allows(scope) else "denied"
            if scope == Scope.STUDIES_COURSES:
                typer.echo(
                    f"{scope.value}: configured {configured}; "
                    "study names, public catalog and course curriculum positions available"
                )
            else:
                typer.echo(
                    f"{scope.value}: configured {configured}; unavailable (reader not verified)"
                )
        return
    if not interactive_terminal():
        raise CampusError(Code.ACTION_REQUIRED, "Run this command in an interactive terminal.")
    from tum_mcp.ui import terminal_console

    console = terminal_console()
    for line in context:
        console.print(line)
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
