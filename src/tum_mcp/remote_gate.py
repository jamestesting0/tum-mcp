"""Release gate: local protocol tests do not establish a trusted host approval UI."""

from tum_mcp.errors import CampusError, Code

# Intentionally unavailable in this development build. Changing a preference,
# fabricating a tool argument, or importing an encrypted grant cannot enable it.
REMOTE_ACTIONS_VERIFIED = False


def require_verified_boundary() -> None:
    if not REMOTE_ACTIONS_VERIFIED:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Remote actions are unavailable until trusted host approval and practice checks pass.",
        )
