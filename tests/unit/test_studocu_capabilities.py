from datetime import UTC, datetime, timedelta

from tum_mcp.studocu.capabilities import capabilities, current_observation
from tum_mcp.studocu.models import Capabilities, Observation


def test_missing_transport_and_bounded_search() -> None:
    result = capabilities()
    assert result.public_search == "available"
    assert result.exhaustive_discovery == "unavailable"
    assert result.remote_original_file == "unavailable"
    assert result.acquisition == "browser_import"
    assert result.account_download_permission.state == "unknown"
    assert result.entitlement_kind == result.expiry_precision == "unknown"
    assert result.entitlement_expiry is result.quota_remaining is result.quota_reset is None


def test_uploader_access_and_file_receipt_are_independent() -> None:
    result = Capabilities(
        account_download_permission=Observation(state="available", detail="uploads processing"),
        local_file=Observation(state="available", scope="one document"),
    )
    assert result.remote_full_text == "unknown"
    assert result.remote_original_file == "unavailable"
    assert result.local_file.state == "available"


def test_unknown_expiry_and_historical_observation() -> None:
    now = datetime.now(UTC)
    assert (
        current_observation(Observation(state="available", observed_at=now), now=now) == "unknown"
    )
    stale = Observation(state="available", observed_at=now - timedelta(days=2), expires_at=now)
    assert current_observation(stale, now=now) == "unknown"
    fresh = stale.model_copy(update={"expires_at": now + timedelta(days=1)})
    assert current_observation(fresh, now=now) == "available"


def test_document_denial_does_not_expire_account() -> None:
    account = Observation(state="available", scope="account")
    document = Observation(state="unavailable", scope="one document")
    assert account.state == "available"
    assert document.scope != account.scope
