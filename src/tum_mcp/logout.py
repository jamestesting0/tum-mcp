"""Removal of selected local campus connections, chosen interactively or by name."""

import sys
from typing import assert_never
from urllib.parse import urlsplit

import typer

from tum_mcp.commands.ui import heading, select_many, terminal_console
from tum_mcp.connect import ConnectionResult, ServiceChoice
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.settings import Account, Provider, preferences
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.onboarding import disconnect
from tum_mcp.tumonline.policy import PolicyStore

REMOTE_NOTE = "Website sessions and API keys are not revoked."


def saved_connections() -> list[tuple[ConnectionResult, str]]:
    targets: list[tuple[ConnectionResult, str]] = []
    paths = Paths.default()
    if paths.file("local-session/session.enc").is_file() or paths.file("session.enc").is_file():
        targets.append((ConnectionResult(ServiceChoice.MOODLE), "Moodle"))
    accounts = preferences().accounts
    for provider in Provider:
        service = ServiceChoice(provider.value)
        saved = [account for account in accounts if account.provider == provider]
        hosts = [urlsplit(account.origin).hostname for account in saved]
        for index, account in enumerate(saved, 1):
            # Hosts tell accounts apart without printing the campus identity they belong to.
            detail = hosts[index - 1] if len(set(hosts)) == len(hosts) else index
            label = service.label + (f" ({detail})" if len(saved) > 1 else "")
            targets.append((ConnectionResult(service, account), label))
    policies = PolicyStore.snapshot()
    for index, policy in enumerate(policies, 1):
        label = "TUMonline" + (f" (account {index})" if len(policies) > 1 else "")
        targets.append(
            (
                ConnectionResult(ServiceChoice.TUMONLINE, AccountRef(account_id=policy.account_id)),
                label,
            )
        )
    return targets


def remove(target: ConnectionResult) -> None:
    match target.account:
        case None:
            paths = Paths.default()
            for storage in ("file", "native"):
                path = paths.file(
                    "local-session/session.enc" if storage == "file" else "session.enc"
                )
                if path.is_file():
                    SessionStore(paths, storage=storage).logout()
        case AccountRef():
            disconnect(target.account)
        case Account():
            Vault().logout(target.account)
        case unreachable:
            assert_never(unreachable)


def account_key(target: ConnectionResult) -> str | None:
    match target.account:
        case None:
            return None
        case AccountRef():
            return target.account.account_id
        case Account():
            return target.account.id
        case unreachable:
            assert_never(unreachable)


def logout_named(service: ServiceChoice, account_id: str | None) -> None:
    matches = [
        (target, label) for target, label in saved_connections() if target.service == service
    ]
    if account_id is not None:
        matches = [
            (target, label) for target, label in matches if account_key(target) == account_id
        ]
    if not matches:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"No saved {service.label} connection"
            + (f" with account {account_id}" if account_id else "")
            + ". Run tum-mcp logout without arguments to see saved connections.",
        )
    if len(matches) > 1:
        accounts = ", ".join(str(account_key(target)) for target, _ in matches)
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Several {service.label} accounts are saved; add one of: {accounts}.",
        )
    target, label = matches[0]
    remove(target)
    typer.echo(f"Removed {label} from this computer. {REMOTE_NOTE}")


def choose_logout() -> None:
    if not sys.stdin.isatty():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Run tum-mcp logout in an interactive terminal, or name a service.",
        )
    console = terminal_console()
    heading(console, "Logout")
    targets = saved_connections()
    if not targets:
        console.print("No saved connections.")
        return
    try:
        selected = select_many(
            "Choose connections to remove",
            tuple((target, label, None, True) for target, label in targets),
        )
    except (EOFError, KeyboardInterrupt):
        selected = None
    if not selected:
        console.print("Cancelled. Connections were not changed.")
        raise typer.Exit(130)
    for target in selected:
        remove(target)
    from tum_mcp.browser_profiles import read_preferences
    from tum_mcp.commands.choices import choose
    from tum_mcp.profile_logout import clear_saved_signins

    cleared = False
    if read_preferences().profiles:
        try:
            cleared = choose(
                "Saved browser profiles",
                (
                    (False, "Keep their TUM sign-in"),
                    (True, "Sign them out too (signs out of every TUM site)"),
                ),
            )
        except (KeyboardInterrupt, EOFError):
            cleared = False
        if cleared:
            clear_saved_signins(tuple(target.service for target in selected))
    labels = ", ".join(label for target, label in targets if target in selected)
    console.print(
        f"Removed {labels} from this computer."
        + (" Saved browser profiles were signed out." if cleared else "")
    )
    console.print(REMOTE_NOTE)
