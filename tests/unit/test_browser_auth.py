import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import httpx2
import pytest
from keyring.backend import KeyringBackend

from tum_mcp import connect
from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError
from tum_mcp.settings import ARTEMIS, ZULIP, Account, Provider, preferences
from tum_mcp.transport import API
from tum_moodle.auth import Cookie


def test_zulip_browser_reads_use_session_json_routes_without_api_keys() -> None:
    account = Account(provider=Provider.ZULIP, origin=ZULIP, principal="7", channels=(42,))
    session = Credential(
        account_id=account.id,
        authentication="browser_session",
        cookies=(
            Cookie(name="sessionid", value="synthetic-browser-secret", domain="zulip.cit.tum.de"),
        ),
    )
    visited: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        visited.append(request.url.path)
        assert request.method == "GET"
        assert request.url.host == "zulip.cit.tum.de"
        assert "authorization" not in request.headers
        assert request.headers["cookie"] == "sessionid=synthetic-browser-secret"
        return httpx2.Response(200, json={"user_id": 7, "email": "fixture@example.invalid"})

    api = API(account, session, httpx2.MockTransport(handler))
    assert json.loads(api.get("/api/v1/users/me"))["user_id"] == 7
    with pytest.raises(CampusError, match="not an enabled read"):
        api.get("/json/users/me/api_key/regenerate")
    assert visited == ["/json/users/me"]
    assert "synthetic-browser-secret" not in session.model_dump_json()


def test_expired_zulip_browser_session_never_requests_a_key_or_follows_redirects() -> None:
    account = Account(provider=Provider.ZULIP, origin=ZULIP, principal="7")
    session = Credential(
        account_id=account.id,
        authentication="browser_session",
        cookies=(Cookie(name="sessionid", value="expired", domain="zulip.cit.tum.de"),),
    )
    visited: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        visited.append(str(request.url))
        return httpx2.Response(401, json={"result": "error", "msg": "Not logged in"})

    with pytest.raises(CampusError, match="AUTH_REQUIRED"):
        API(account, session, httpx2.MockTransport(handler)).get("/api/v1/users/me")
    assert visited == [ZULIP + "/json/users/me"]


def test_one_temporary_context_connects_both_services_and_discards_idp_cookies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_keyring: KeyringBackend,
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    manager = MagicMock()
    browser = manager.return_value.__enter__.return_value.chromium.launch.return_value
    context = browser.new_context.return_value
    payloads = {
        ARTEMIS + "/api/core/public/account": {"id": 7, "login": "fixture"},
        ZULIP + "/json/users/me": {"user_id": 8, "email": "fixture@example.invalid"},
    }

    def browser_get(url: str, *, max_redirects: int, timeout: int) -> MagicMock:
        assert max_redirects == 0 and timeout == 10000
        response = MagicMock(status=200)
        response.body.return_value = json.dumps(payloads[url]).encode()
        return response

    def cookies(origin: str) -> list[dict[str, str]]:
        return [
            {"name": "service", "value": "synthetic-session", "domain": urlsplit(origin).hostname},
            {"name": "idp", "value": "never-persist-idp", "domain": ".tum.de"},
            {"name": "idp2", "value": "never-persist-idp", "domain": "login.tum.de"},
        ]

    context.request.get.side_effect = browser_get
    context.cookies.side_effect = cookies
    monkeypatch.setattr(connect, "sync_playwright", manager)

    def api(account: Account, credential: Credential) -> API:
        def handler(request: httpx2.Request) -> httpx2.Response:
            assert "never-persist-idp" not in request.headers.get("cookie", "")
            return httpx2.Response(200, json=payloads[str(request.url)])

        return API(account, credential, httpx2.MockTransport(handler))

    monkeypatch.setattr(connect, "API", api)
    accounts = connect.connect_browser((Provider.ARTEMIS, Provider.ZULIP))
    assert {account.provider for account in accounts} == {Provider.ARTEMIS, Provider.ZULIP}
    assert len(preferences().accounts) == 2
    assert browser.new_context.call_count == 1
    browser.close.assert_called_once()
    for account in accounts:
        saved = Vault().load(account)
        assert saved.authentication == "browser_session"
        assert len(saved.cookies) == 1
        assert saved.cookies[0].domain == urlsplit(account.origin).hostname
        assert saved.api_key.get_secret_value() == ""
