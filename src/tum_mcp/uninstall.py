"""Remove only unchanged managed registrations and files; retain user campus data."""

import errno
import hashlib
from pathlib import Path

from filelock import FileLock
from pydantic import ValidationError

from tum_mcp import __version__
from tum_mcp.client_config import Marketplace, client_config_path, read_client_config
from tum_mcp.client_hosts import ClientHost, client_home, client_launch
from tum_mcp.client_installs import (
    ClientName,
    Installation,
    Write,
    commit_writes,
    load_receipt,
    managed_writes,
    read_owned_file,
    receipt_path,
)
from tum_mcp.client_rendering import rendered_client
from tum_mcp.errors import CampusError, Code
from tum_mcp.legacy_clients import legacy_installation
from tum_mcp.settings import config_dir


def uninstall_client(
    name: ClientName, home: Path | None = None, *, host: ClientHost = ClientHost.LOCAL
) -> bool:
    with FileLock(str(config_dir() / "client-install.lock")):
        return _uninstall_client(name, home, host=host)


def _uninstall_client(name: ClientName, home: Path | None, *, host: ClientHost) -> bool:
    base = client_home(host, home).resolve()
    target = client_config_path(name, base, host=host)
    root = base if target.is_relative_to(base) else config_dir().resolve()
    before = read_owned_file(target, root)
    config = read_client_config(target, for_update=True)
    entry = config.mcpServers.get("tum")
    previous = load_receipt(name, host, base)
    if previous is None and entry is None:
        print(f"{name.title()}: no managed registration to remove.")
        return False
    if previous is None:
        desired, server, catalog, _ = rendered_client(name, client_launch(host), host)
        previous = legacy_installation(name, host, base, entry, server)
        if previous is None and entry == server:
            previous = Installation(
                client=name,
                host=host,
                home=base,
                version=__version__,
                server=server,
                files={key: hashlib.sha256(value).hexdigest() for key, value in desired.items()},
                catalog=catalog,
            )
    if previous is None or entry is not None and entry != previous.server:
        raise CampusError(Code.WORKSPACE_CONFLICT, "A customized MCP configuration was preserved.")
    writes = list(managed_writes(base, {}, previous))
    config.mcpServers.pop("tum", None)
    value = config.model_dump()
    after = config.model_dump_json(indent=2).encode()
    if (
        name in {"generic", "codex"}
        and not config.mcpServers
        and set(value) <= {"mcpServers", "$schema"}
    ):
        after = None
    writes.append(Write(target, before, after if before is not None else None))
    if name == "codex":
        path = base / ".agents/plugins/marketplace.json"
        current = read_owned_file(path, base)
        if current is not None:
            try:
                market = Marketplace.model_validate_json(current)
            except ValidationError:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Invalid plugin marketplace preserved for review."
                ) from None
            owned = [plugin for plugin in market.plugins if plugin.get("name") == "tum-mcp"]
            if any(plugin != previous.catalog for plugin in owned):
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Customized marketplace entry was preserved."
                )
            market.plugins = [
                plugin for plugin in market.plugins if plugin.get("name") != "tum-mcp"
            ]
            writes.append(Write(path, current, market.model_dump_json(indent=2).encode()))
    record = receipt_path(name, host, base)
    writes.append(Write(record, record.read_bytes() if record.is_file() else None, None))
    commit_writes(tuple(writes))
    _prune_empty_directories(base, previous)
    print(f"{name.title()}: managed registration and unchanged skill files removed.")
    if name == "codex":
        print("Remove/disable the cached TUM MCP plugin in Codex Plugins, then restart.")
    print("Campus sessions, settings, downloads and assignment work were preserved.")
    return True


def _prune_empty_directories(base: Path, previous: Installation) -> None:
    boundary = base / (".codex/plugins/local" if previous.client == "codex" else ".claude/skills")
    directories: set[Path] = set()
    for relative in previous.files:
        parent = (base / relative).parent
        while parent != boundary and parent.is_relative_to(boundary):
            directories.add(parent)
            parent = parent.parent
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError as error:
            if error.errno not in {errno.ENOTEMPTY, errno.ENOENT}:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Empty client directories need local cleanup."
                ) from None
