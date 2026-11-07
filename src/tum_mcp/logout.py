"""Interactive removal of selected local campus connections."""

import sys
from typing import assert_never

import typer

from tum_mcp.commands.ui import State, heading, select_many, terminal_console
from tum_mcp.connect import ConnectionResult, ServiceChoice
from tum_mcp.credentials import Vault
from tum_mcp.diagnostics import collect_services
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.settings import Account, Provider, preferences
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.onboarding import disconnect
from tum_mcp.tumonline.policy import PolicyStore


def choose_logout() -> None:
    if not sys.stdin.isatty():
        raise CampusError(
            Code.ACTION_REQUIRED, "Run logout in an interactive terminal or name an account."
        )
    console = terminal_console()
    heading(console, "Logout", "Choose local connections to remove. Remote sessions are retained.")
    report = collect_services(live="stale")
    checks = {check.label: check for check in report.services}
    targets: list[tuple[ConnectionResult, str]] = []
    paths = Paths.default()
    if paths.file("local-session/session.enc").is_file() or paths.file("session.enc").is_file():
        targets.append((ConnectionResult(ServiceChoice.MOODLE), "Moodle"))
    accounts = preferences().accounts
    for provider in Provider:
        service = ServiceChoice(provider.value)
        saved = [account for account in accounts if account.provider == provider]
        for index, account in enumerate(saved, 1):
            label = service.label + (f" {index}" if len(saved) > 1 else "")
            targets.append((ConnectionResult(service, account), label))
    for index, policy in enumerate(policies := PolicyStore.snapshot(), 1):
        label = "TUMonline" + (f" {index}" if len(policies) > 1 else "")
        targets.append(
            (
                ConnectionResult(ServiceChoice.TUMONLINE, AccountRef(account_id=policy.account_id)),
                label,
            )
        )
    if not targets:
        console.print("No saved connections.")
        return
    try:
        selected = select_many(
            "Choose connections",
            tuple(
                (target, label, checks[label].state if label in checks else State.DISABLED, True)
                for target, label in targets
            ),
        )
    except (EOFError, KeyboardInterrupt):
        selected = None
    if not selected:
        console.print("Cancelled. Connections were not changed.")
        raise typer.Exit(130)
    for target in selected:
        match target.account:
            case None:
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
        console.print(f"Disconnected {target.service.label}.")
    from tum_mcp.browser_profiles import read_preferences
    from tum_mcp.commands.choices import choose
    from tum_mcp.profile_logout import clear_saved_signins

    if read_preferences().profiles:
        console.print("Clearing saved browser sign-in also clears shared TUM sign-in.")
        try:
            clear = choose(
                "Saved browser sign-in",
                (
                    (False, "Keep"),
                    (True, "Clear for the selected services"),
                ),
            )
        except (KeyboardInterrupt, EOFError):
            clear = False
        if clear:
            clear_saved_signins(tuple(target.service for target in selected))
            console.print("Saved browser sign-in cleared.")
