from enum import StrEnum

from mcp.server.mcpserver.exceptions import ToolError


class Code(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    SCOPE_DENIED = "SCOPE_DENIED"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    STALE_RESULT = "STALE_RESULT"
    PENDING = "PENDING"
    RATE_LIMITED = "RATE_LIMITED"
    WORKSPACE_CONFLICT = "WORKSPACE_CONFLICT"
    OFFLINE = "OFFLINE"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class CampusError(ToolError):
    def __init__(self, code: Code, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
