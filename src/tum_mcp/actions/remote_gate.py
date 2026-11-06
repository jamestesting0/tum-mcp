"""Retired action gate. This package provides read-only campus access."""

from tum_mcp.errors import CampusError, Code

# Kept for compatibility with old local state; it cannot enable an executor.
REMOTE_ACTIONS_VERIFIED = False


def require_verified_boundary() -> None:
    raise CampusError(
        Code.CAPABILITY_UNSUPPORTED,
        "Campus access is read-only. Exercise start, push, submission and rebuild are unavailable.",
    )
