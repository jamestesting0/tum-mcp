import json
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError
from tum_mcp.settings import Account, Provider
from tum_mcp.transport import API
from tum_mcp.zulip import Zulip
from tum_mcp.zulip_models import Query


@pytest.fixture
def account() -> Account:
    return Account(
        provider=Provider.ZULIP, origin="https://zulip.cit.tum.de", principal="7", channels=(42,)
    )


def credential(account: Account) -> Credential:
    return Credential(
        account_id=account.id,
        username=SecretStr("student@example.invalid"),
        api_key=SecretStr("private-api-key"),
    )


def test_vault_encrypts_and_binds_credentials_when_accounts_differ(
    tmp_path: Path,
    memory_keyring,
    account: Account,
) -> None:
    # Given an OS-keyring-backed vault and one identity.
    vault = Vault(tmp_path)
    saved = credential(account)
    vault.save(account, saved)
    # When credentials are loaded for the saved account.
    loaded = vault.load(account)
    # Then only the same identity can use them and disk/normal representations hide secrets.
    assert loaded.api_key.get_secret_value() == "private-api-key"
    assert b"private-api-key" not in (tmp_path / f"{account.id}.enc").read_bytes()
    assert "private-api-key" not in repr(loaded)
    assert "private-api-key" not in loaded.model_dump_json()
    with pytest.raises(CampusError, match="principal"):
        vault.save(account.model_copy(update={"principal": "8"}), saved)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/messages/flags",
        "/api/v1/users/me/api_key",
        "https://example.invalid",
        "/api/v1/messages?target=elsewhere",
    ],
)
def test_transport_denies_unlisted_endpoints_before_network(account: Account, path: str) -> None:
    # Given an endpoint outside the read allowlist.
    api = API(account, credential(account))
    # When it is requested, then no transport call can occur.
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        api.get(path)


def test_transport_rejects_cross_origin_redirect(account: Account) -> None:
    # Given an authenticated request redirected to an external origin.
    visited: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        visited.append(str(request.url))
        return httpx2.Response(302, headers={"Location": "https://external.invalid/collect"})

    api = API(account, credential(account), httpx2.MockTransport(handler))
    # When the request is made, then the destination never receives credentials.
    with pytest.raises(CampusError, match="redirect"):
        api.get("/api/v1/users/me")
    assert visited == ["https://zulip.cit.tum.de/api/v1/users/me"]


def zulip_api(account: Account, *, private: bool = False, wrong_message: bool = False) -> API:
    routes = {
        "/api/v1/users/me": {"user_id": 7, "email": "student@example.invalid"},
        "/api/v1/streams": {
            "streams": [{"stream_id": 42, "name": "Course", "invite_only": private}]
        },
        "/api/v1/messages": {
            "found_oldest": False,
            "found_newest": True,
            "messages": [
                {
                    "id": 100,
                    "type": "private" if wrong_message else "stream",
                    "stream_id": 42,
                    "subject": "Homework",
                    "content": "<p>Use the updated statement.</p>",
                    "sender_id": 4,
                    "sender_full_name": "Instructor",
                    "timestamp": 1000,
                }
            ],
        },
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        if "narrow" in request.url.params:
            narrow = json.loads(request.url.params["narrow"])
            assert narrow[0] == {"operator": "stream", "operand": 42}
        assert request.url.path in routes
        return httpx2.Response(200, json=routes[request.url.path])

    return API(account, credential(account), httpx2.MockTransport(handler))


def test_zulip_search_preserves_scope_and_returns_partial_coverage(account: Account) -> None:
    # Given a permitted channel with more retained history.
    provider = Zulip(zulip_api(account))
    # When one page is searched.
    page = provider.messages(Query(channel_id=42, query="statement"))
    # Then evidence is cited and pagination cannot be reused for another query.
    assert page.coverage_status == "partial"
    assert page.next_cursor is not None
    assert page.messages[0].text == "Use the updated statement."
    assert page.messages[0].source_link.endswith("/near/100")
    with pytest.raises(CampusError, match="different query"):
        provider.messages(Query(channel_id=42, query="other", cursor=page.next_cursor))


@pytest.mark.parametrize("private,wrong_message", [(True, False), (False, True)])
def test_zulip_rejects_private_scope_and_dm_leaks(
    account: Account, private: bool, wrong_message: bool
) -> None:
    # Given private content without its separate scope grant.
    provider = Zulip(zulip_api(account, private=private, wrong_message=wrong_message))
    # When a direct tool-style request bypasses all skill instructions, then policy still holds.
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        provider.messages(Query(channel_id=42))


def test_zulip_denies_unselected_channel_before_account_access(account: Account) -> None:
    # Given a connected identity without local access to channel 43.
    provider = Zulip(API(account))
    # When it is searched, then the request is rejected before loading credentials.
    with pytest.raises(CampusError, match="Enable this channel"):
        provider.messages(Query(channel_id=43))


def test_catch_up_checkpoint_contains_no_message_text_and_rechecks_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account: Account,
) -> None:
    # Given an accessible channel and isolated checkpoint state.
    from tum_mcp.checkpoints import get_checkpoint, save_checkpoint

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    provider = Zulip(zulip_api(account))
    # When the completed summary advances its integration-owned checkpoint.
    saved = save_checkpoint(provider, 42, 100)
    # Then only identifiers persist and a revoked scope cannot read the checkpoint.
    assert saved.message_id == 100
    assert get_checkpoint(provider, 42).message_id == 100
    path = next((tmp_path / "checkpoints").glob("*.json"))
    assert b"Use the updated statement" not in path.read_bytes()
    revoked = account.model_copy(update={"channels": ()})
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        get_checkpoint(Zulip(zulip_api(revoked)), 42)
