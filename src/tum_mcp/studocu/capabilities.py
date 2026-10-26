"""Conservative interpretation of observed access, independent of remote transport."""

from datetime import UTC, datetime

from tum_mcp.studocu.models import Availability, Capabilities, Observation


def current_observation(observation: Observation, *, now: datetime | None = None) -> Availability:
    """A historical observation or date without timezone cannot assert current access."""
    now = now or datetime.now(UTC)
    if observation.observed_at is None or observation.observed_at.tzinfo is None:
        return "unknown"
    if observation.expires_at is None or observation.expires_at.tzinfo is None:
        return "unknown"
    if now.tzinfo is None or observation.observed_at > now or observation.expires_at <= now:
        return "unknown"
    return observation.state


def capabilities() -> Capabilities:
    """Report established transport support, without inferring an account entitlement."""
    return Capabilities()
