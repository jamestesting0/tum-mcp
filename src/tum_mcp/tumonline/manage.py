"""Local TUMonline permission controls and capability status."""

import sys
from typing import Annotated

import questionary
import typer

from tum_mcp.errors import CampusError, Code
from tum_mcp.tumonline.policy import PolicyStore, Scope

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def interactive_terminal() -> bool:
    return sys.stdin.isatty()


def choose_studies(current: bool) -> bool | None:
    return questionary.confirm(
        "Allow study names, public courses and public curriculum positions?", default=current
    ).unsafe_ask()


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
    typer.echo(f"Policy account: {account}")
    typer.echo("These permissions apply to all MCP clients sharing this configuration.")
    typer.echo("Other providers and local programs are outside this policy's control.")
    for scope in Scope:
        configured = "allowed" if policy.allows(scope) else "denied"
        if scope == Scope.STUDIES_COURSES:
            typer.echo(
                f"{scope.value}: configured {configured}; "
                "study names, public catalog and course curriculum positions available"
            )
        else:
            typer.echo(f"{scope.value}: configured {configured}; unavailable (reader not verified)")
    if show:
        return
    if not interactive_terminal():
        raise CampusError(Code.ACTION_REQUIRED, "Run this command in an interactive terminal.")
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
