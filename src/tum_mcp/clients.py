"""Conflict-safe activation of rendered client files, backed by ownership receipts."""

import hashlib
from pathlib import Path

from filelock import FileLock
from pydantic import TypeAdapter, ValidationError

from tum_mcp import __version__
from tum_mcp.client_config import CLIENTS as CLIENTS
from tum_mcp.client_config import ClientConfiguration, Marketplace
from tum_mcp.client_config import client_config_path as client_config_path
from tum_mcp.client_config import read_client_config as read_client_config
from tum_mcp.client_hosts import ClientHost, client_home, client_launch
from tum_mcp.client_installs import (
    ClientName,
    Installation,
    Write,
    commit_writes,
    load_receipt,
    managed_writes,
    prune_removed_folders,
    read_owned_file,
    receipt_path,
)
from tum_mcp.client_rendering import rendered_client
from tum_mcp.client_rendering import same_tree as same_tree
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import config_dir, data_path
from tum_mcp.skills import LEGACY_SKILLS, inspect_skills


def install_client(
    name: str,
    home: Path | None = None,
    *,
    host: ClientHost = ClientHost.LOCAL,
    announce: bool = True,
) -> None:
    try:
        selected = TypeAdapter(ClientName).validate_python(name)
    except ValidationError:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Choose a supported MCP client.") from None
    if (data_path() / "runtime-removal.pending").exists():
        raise CampusError(
            Code.ACTION_REQUIRED, "Runtime removal is pending; rerun npm setup to recover."
        )
    base = client_home(host, home).resolve()
    launch = client_launch(host)
    with FileLock(str(config_dir() / "client-install.lock")):
        if selected == "codex" and any(
            (base / ".agents/skills" / item["name"]).exists()
            for item in [*inspect_skills(), *({"name": name} for name in LEGACY_SKILLS)]
        ):
            raise CampusError(Code.WORKSPACE_CONFLICT, "Duplicate global campus skill; review it.")
        desired, server, catalog, messages = rendered_client(selected, launch, host)
        target = client_config_path(selected, base, host=host)
        target_root = base if target.is_relative_to(base) else config_dir().resolve()
        before = read_owned_file(target, target_root)
        config = read_client_config(target, for_update=True)
        existing = config.mcpServers.get("tum")
        previous = load_receipt(selected, host, base)
        if previous is None and existing is not None:
            from tum_mcp.legacy_clients import legacy_installation

            previous = legacy_installation(selected, host, base, existing, server)
        if (
            existing is not None
            and existing != server
            and (previous is None or existing != previous.server)
        ):
            raise CampusError(Code.WORKSPACE_CONFLICT, "A customized MCP entry was preserved.")
        writes = list(managed_writes(base, desired, previous))
        config.mcpServers["tum"] = server
        if selected == "codex" and "$schema" not in config.model_extra:
            config = ClientConfiguration.model_validate(
                config.model_dump()
                | {"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"}
            )
        writes.append(Write(target, before, config.model_dump_json(indent=2).encode()))
        if catalog is not None:
            path = base / ".agents/plugins/marketplace.json"
            old_catalog = read_owned_file(path, base)
            try:
                market = (
                    Marketplace.model_validate_json(old_catalog) if old_catalog else Marketplace()
                )
            except ValidationError:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Invalid plugin marketplace preserved."
                ) from None
            owned = [entry for entry in market.plugins if entry.get("name") == "tum-mcp"]
            if (
                len(owned) > 1
                or owned
                and owned[0] != catalog
                and (previous is None or owned[0] != previous.catalog)
            ):
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Customized plugin marketplace preserved."
                )
            market.plugins = [
                entry for entry in market.plugins if entry.get("name") != "tum-mcp"
            ] + [catalog]
            writes.append(Write(path, old_catalog, market.model_dump_json(indent=2).encode()))
        receipt = Installation(
            client=selected,
            host=host,
            home=base,
            version=__version__,
            server=server,
            files={name: hashlib.sha256(data).hexdigest() for name, data in desired.items()},
            catalog=catalog,
        )
        record = receipt_path(selected, host, base)
        record_before = read_owned_file(record, config_dir().resolve())
        writes.append(Write(record, record_before, receipt.model_dump_json(indent=2).encode()))
        commit_writes(tuple(writes))
        if previous:
            prune_removed_folders(base, tuple(set(previous.files) - set(desired)))
        if announce:
            print(f"{selected.title()} registration saved for this runtime.")
            print(messages)
