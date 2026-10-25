"""Refresh registered clients from their last known managed content, without campus reads."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import ValidationError

from tum_mcp.client_hosts import ClientHost, client_home
from tum_mcp.client_installs import ClientName, Installation, load_receipt, receipt_path
from tum_mcp.clients import CLIENTS, client_config_path, install_client, read_client_config
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import BrowserSetupError, is_wsl
from tum_mcp.settings import config_path


@dataclass(frozen=True, slots=True)
class ClientUpdate:
    client: str
    host: str
    state: Literal["updated", "needs_review", "not_registered", "skipped"]
    detail: str


class ClientUpdateInfo(TypedDict):
    client: str
    host: str
    state: Literal["updated", "needs_review", "not_registered", "skipped"]
    detail: str


class UpdateSummary(TypedDict):
    updated: int
    needs_review: int
    clients: list[ClientUpdateInfo]


def installation_targets() -> tuple[
    tuple[tuple[ClientName, ClientHost, Path], ...], list[ClientUpdate]
]:
    targets: set[tuple[ClientName, ClientHost, Path]] = set()
    results: list[ClientUpdate] = []
    directory = config_path() / "clients"
    for path in sorted(directory.glob("*.json")):
        try:
            record = Installation.model_validate_json(path.read_bytes())
            if path != receipt_path(record.client, record.host, record.home):
                raise CampusError(Code.WORKSPACE_CONFLICT, "Installation record name is invalid.")
            load_receipt(record.client, record.host, record.home)
            targets.add((record.client, record.host, record.home))
        except (OSError, ValidationError, CampusError):
            results.append(
                ClientUpdate(
                    "Installation record",
                    "local",
                    "needs_review",
                    "Invalid record preserved; inspect the local clients directory.",
                )
            )
    profiles = [(ClientHost.LOCAL, Path.home().resolve())]
    if is_wsl():
        try:
            profiles.append((ClientHost.WINDOWS, client_home(ClientHost.WINDOWS).resolve()))
        except BrowserSetupError as error:
            results.append(ClientUpdate("Windows discovery", "windows", "skipped", error.message))
    for host, home in profiles:
        for name in CLIENTS:
            target = client_config_path(name, home, host=host)
            if target.exists():
                targets.add((name, host, home))
    return tuple(sorted(targets)), results


def refresh_clients() -> UpdateSummary:
    targets, results = installation_targets()
    for name, host, home in targets:
        try:
            target = client_config_path(name, home, host=host)
            current = read_client_config(target, for_update=True)
            if current.mcpServers.get("tum") is None:
                results.append(
                    ClientUpdate(
                        name, host.value, "not_registered", "No tum entry; it was not re-created."
                    )
                )
                continue
            # The adapter preflights every managed file before applying any change.
            install_client(name, home, host=host, announce=False)
            results.append(
                ClientUpdate(
                    name,
                    host.value,
                    "updated",
                    "Managed registration refreshed. Reload/restart the client.",
                )
            )
        except (CampusError, BrowserSetupError) as error:
            results.append(ClientUpdate(name, host.value, "needs_review", error.message))
        except OSError:
            results.append(
                ClientUpdate(
                    name,
                    host.value,
                    "needs_review",
                    "Client files could not be accessed; they were preserved.",
                )
            )
    return {
        "updated": sum(item.state == "updated" for item in results),
        "needs_review": sum(item.state == "needs_review" for item in results),
        "clients": [
            ClientUpdateInfo(
                client=item.client, host=item.host, state=item.state, detail=item.detail
            )
            for item in results
        ],
    }
