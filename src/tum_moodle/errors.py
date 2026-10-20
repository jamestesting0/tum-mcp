from enum import StrEnum

from mcp.server.mcpserver.exceptions import ToolError


class ErrorCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    OFFLINE = "OFFLINE"
    RATE_LIMITED = "RATE_LIMITED"
    RESOURCE_UNSUPPORTED = "RESOURCE_UNSUPPORTED"
    NEEDS_OCR = "NEEDS_OCR"
    TOO_LARGE = "TOO_LARGE"
    UNSAFE_URL = "UNSAFE_URL"
    SETUP_REQUIRED = "SETUP_REQUIRED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


class MoodleError(ToolError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
