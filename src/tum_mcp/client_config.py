"""Client configuration paths and schema, independent of runtime management."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from tum_mcp.client_hosts import ClientHost
from tum_mcp.client_installs import ClientName
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import config_dir

CLIENTS: tuple[ClientName, ...] = ("codex", "claude", "cursor", "antigravity", "generic")


class ClientConfiguration(BaseModel):
    model_config = ConfigDict(extra="allow")
    mcpServers: dict[str, JsonValue] = Field(default_factory=dict)


def client_config_path(name: str, home: Path, *, host: ClientHost = ClientHost.LOCAL) -> Path:
    match name:
        case "cursor":
            return home / ".cursor/mcp.json"
        case "antigravity":
            current = home / ".gemini/config/mcp_config.json"
            legacy = home / ".gemini/antigravity/mcp_config.json"
            return legacy if legacy.is_file() and not current.exists() else current
        case "claude":
            return home / ".claude.json"
        case "generic":
            return (
                home / ".config/tum-mcp/mcp-wsl.json"
                if host == ClientHost.WINDOWS
                else config_dir() / "mcp.json"
            )
        case "codex":
            return home / ".codex/plugins/local/tum-mcp/mcp.json"
        case _:
            raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Choose a supported MCP client.")


def read_client_config(path: Path, *, for_update: bool = False) -> ClientConfiguration:
    if for_update and path.is_symlink():
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Client configuration is a symbolic link; update its target manually.",
        )
    if not path.exists():
        return ClientConfiguration()
    try:
        return ClientConfiguration.model_validate_json(path.read_bytes())
    except (ValidationError, OSError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Client configuration is invalid; preserve and repair it locally.",
        ) from None


class Marketplace(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = "personal-local"
    plugins: list[dict[str, JsonValue]] = Field(default_factory=list)
