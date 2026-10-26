import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import httpx2
import pytest

from tum_mcp import connect
from tum_mcp.connect import ServiceChoice
from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError
from tum_mcp.moodle import auth
from tum_mcp.moodle.auth import SessionStore
from tum_mcp.moodle.browsers import BrowserChoice
from tum_mcp.moodle.config import BASE_URL, Paths
from tum_mcp.settings import ARTEMIS, ZULIP, Account, Provider, preferences, save_account
from tum_mcp.transport import API


@pytest.mark.parametrize(
    "selected",
    [
        (ServiceChoice.MOODLE,),
        (ServiceChoice.ARTEMIS,),
        (ServiceChoice.ZULIP,),
        (ServiceChoice.TUMONLINE,),
        (ServiceChoice.MOODLE, ServiceChoice.ZULIP),
        tuple(ServiceChoice),
    ],
)
def test_only_selected_tabs_open_and_all_sessions_use_local_files(
    selected: tuple[ServiceChoice, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr(auth, "system_keyring", lambda: pytest.fail("No native-store reads"))
    manager = MagicMock()
    browser = manager.return_value.__enter__.return_value.chromium.launch.return_value
    context = browser.new_context.return_value
    payloads = {
        BASE_URL + "/my/courses.php": b'<a href="logout.php">Logout</a>',
        ARTEMIS + "/api/core/public/account": b'{"id":7,"login":"fixture"}',
        ZULIP + "/json/users/me": b'{"user_id":8,"email":"fixture@example.invalid"}',
    }

    def browser_get(url: str, **kwargs: object) -> MagicMock:
        assert kwargs == {"max_redirects": 0, "timeout": 10000}
        response = MagicMock(status=200)
        response.body.return_value = payloads[url]
        return response

    context.request.get.side_effect = browser_get
    context.cookies.side_effect = lambda origin: [
        {"name": "session", "value": "synthetic-only", "domain": urlsplit(origin).hostname},
        {"name": "idp", "value": "never-retain", "domain": ".tum.de"},
    ]
    monkeypatch.setattr(connect, "sync_playwright", manager)

    def api(account: Account, credential: Credential) -> API:
        return API(
            account,
            credential,
            httpx2.MockTransport(
                lambda request: httpx2.Response(200, content=payloads[str(request.url)])
            ),
        )

    monkeypatch.setattr(connect, "API", api)
    from tum_mcp.tumonline import onboarding
    from tum_mcp.tumonline.identity import account_for_subject

    def connect_tumonline(context, attempt):
        account = account_for_subject("synthetic")
        cookie = auth.Cookie(name="session", value="synthetic-only", domain="campus.tum.de")
        Vault().save(account, Credential(account_id=account.id, cookies=(cookie,)))
        return account

    monkeypatch.setattr(onboarding, "connect_context", connect_tumonline)
    completed = []
    results = connect.connect_services(
        selected, on_connected=completed.append, browser=BrowserChoice("Synthetic", "unused")
    )
    origins = {
        ServiceChoice.MOODLE: BASE_URL,
        ServiceChoice.ARTEMIS: ARTEMIS,
        ServiceChoice.ZULIP: ZULIP,
        ServiceChoice.TUMONLINE: "https://campus.tum.de/tumonline/ee/ui/ca2/app/desktop/",
    }
    assert context.new_page.call_count == len(selected)
    assert context.new_page.return_value.goto.call_args_list == [
        ((origins[service],), {"wait_until": "domcontentloaded"}) for service in selected
    ]
    assert tuple(result.service for result in results) == selected
    assert completed == list(results)
    browser.close.assert_called_once()
    for result in results:
        if result.account:
            cookies = Vault().load(result.account).cookies
        else:
            cookies = SessionStore(Paths.default(), storage="file").load().cookies
        assert len(cookies) == 1 and cookies[0].value == "synthetic-only"


@pytest.mark.parametrize("selected", [(), (ServiceChoice.MOODLE, ServiceChoice.MOODLE)])
def test_invalid_selection_cannot_launch_a_browser(
    selected: tuple[ServiceChoice, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(connect, "sync_playwright", lambda: pytest.fail("No browser"))
    with pytest.raises(CampusError, match="exactly once"):
        connect.connect_services(selected)


def test_timeout_preserves_completed_connections_and_closes_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path))
    manager = MagicMock()
    browser = manager.return_value.__enter__.return_value.chromium.launch.return_value
    context = browser.new_context.return_value
    success = MagicMock(status=200)
    success.body.return_value = b"logout.php"
    context.request.get.side_effect = [success, MagicMock(status=401)]
    context.cookies.return_value = [
        {"name": "session", "value": "synthetic-only", "domain": "www.moodle.tum.de"}
    ]
    ticks = iter((0, 1, 601))
    monkeypatch.setattr(connect.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(connect, "sync_playwright", manager)
    with pytest.raises(CampusError, match="completed connections were saved"):
        connect.connect_services(
            (ServiceChoice.MOODLE, ServiceChoice.ZULIP),
            browser=BrowserChoice("Synthetic", "unused"),
        )
    assert SessionStore(Paths.default(), storage="file").load().cookies[0].value == "synthetic-only"
    browser.close.assert_called_once()


def test_reconnect_preserves_settings_changed_during_sign_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    original = Account(
        provider=Provider.ARTEMIS, origin=ARTEMIS, principal="7", workspace_writes=True
    )
    save_account(original)
    stale = preferences().accounts[0]
    save_account(stale.model_copy(update={"workspace_writes": False}))
    revision = preferences().accounts[0].scope_revision
    save_account(stale, preserve_settings=True)
    current = preferences().accounts[0]
    assert not current.workspace_writes and current.scope_revision == revision
    assert "synthetic" not in json.dumps(current.model_dump(mode="json"))
