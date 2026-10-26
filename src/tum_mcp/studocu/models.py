"""Independent evidence for provider, account and file capabilities."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from tum_mcp.settings import Frozen

Availability = Literal["available", "unavailable", "unknown"]


class Observation(Frozen):
    state: Availability = "unknown"
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    scope: str = Field(default="", max_length=200)
    detail: str = Field(default="", max_length=1000)


class Capabilities(Frozen):
    public_search: Availability = "available"
    exhaustive_discovery: Availability = "unavailable"
    delegated_session: Availability = "unknown"
    remote_full_text: Availability = "unknown"
    remote_original_file: Availability = "unavailable"
    account_download_permission: Observation = Field(default_factory=Observation)
    local_file: Observation = Field(default_factory=Observation)
    acquisition: Literal["browser_import"] = "browser_import"
    entitlement_kind: Literal["unknown"] = "unknown"
    entitlement_expiry: None = None
    expiry_precision: Literal["unknown"] = "unknown"
    quota_remaining: None = None
    quota_reset: None = None
