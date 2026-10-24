"""Explicit local onboarding; credential values never pass through MCP arguments."""

import time
from urllib.parse import urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import Page, sync_playwright
from pydantic import SecretStr

from tum_mcp.artemis_models import Identity as ArtemisIdentity
from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.parsing import decode
from tum_mcp.settings import ARTEMIS, ZULIP, Account, Provider, preferences, save_account
from tum_mcp.transport import API, MAX_RESPONSE
from tum_mcp.zulip_models import Identity as ZulipIdentity
from tum_moodle.auth import Cookie


def connect_zulip(email: str, key: SecretStr) -> Account:
    pending = Account(provider=Provider.ZULIP, origin=ZULIP, principal="pending")
    credential = Credential(account_id=pending.id, username=SecretStr(email), api_key=key)
    identity = decode(ZulipIdentity, API(pending, credential).get("/api/v1/users/me"))
    account = existing_account(pending.model_copy(update={"principal": str(identity.user_id)}))
    Vault().replace_login(account, credential.model_copy(update={"account_id": account.id}))
    save_account(account)
    return account


def connect_artemis() -> Account:
    return connect_browser((Provider.ARTEMIS,))[0]


def connect_browser(providers: tuple[Provider, ...]) -> tuple[Account, ...]:
    """One temporary SSO context; persist only each service's own host cookies."""
    connected: list[Account] = []
    if not providers or len(set(providers)) != len(providers):
        raise CampusError(Code.SCOPE_DENIED, "Select each campus provider exactly once.")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            try:
                context = browser.new_context()
                origins = {Provider.ARTEMIS: ARTEMIS, Provider.ZULIP: ZULIP}
                pages: dict[Provider, Page] = {}
                for provider in providers:
                    page = context.new_page()
                    page.goto(origins[provider], wait_until="domcontentloaded")
                    pages[provider] = page
                waiting = set(providers)
                deadline = time.monotonic() + 600
                while time.monotonic() < deadline:
                    for provider in tuple(waiting):
                        origin = origins[provider]
                        path = (
                            "/api/core/public/account"
                            if provider == Provider.ARTEMIS
                            else "/json/users/me"
                        )
                        response = context.request.get(
                            origin + path, max_redirects=0, timeout=10000
                        )
                        if response.status != 200:
                            continue
                        payload = response.body()
                        if len(payload) > MAX_RESPONSE:
                            raise CampusError(
                                Code.INVALID_RESPONSE, "Identity response exceeded budget."
                            )
                        principal = (
                            str(decode(ArtemisIdentity, payload).id)
                            if provider == Provider.ARTEMIS
                            else str(decode(ZulipIdentity, payload).user_id)
                        )
                        account = existing_account(
                            Account(provider=provider, origin=origin, principal=principal)
                        )
                        cookies = tuple(
                            Cookie.model_validate(item)
                            for item in context.cookies(origin)
                            if item["domain"].lstrip(".") == urlsplit(origin).hostname
                        )
                        if not cookies:
                            raise CampusError(
                                Code.AUTH_REQUIRED,
                                "No service-owned session cookie was established.",
                            )
                        credential = Credential(
                            account_id=account.id,
                            authentication="browser_session",
                            cookies=cookies,
                        )
                        # Check the encrypted broker's real HTTP path, not merely the browser page.
                        verification = API(account, credential).get(
                            "/api/core/public/account"
                            if provider == Provider.ARTEMIS
                            else "/api/v1/users/me"
                        )
                        verified_principal = (
                            str(decode(ArtemisIdentity, verification).id)
                            if provider == Provider.ARTEMIS
                            else str(decode(ZulipIdentity, verification).user_id)
                        )
                        if verified_principal != principal:
                            raise CampusError(
                                Code.SCOPE_DENIED, "Identity changed during connection."
                            )
                        Vault().replace_login(account, credential)
                        save_account(account)
                        connected.append(account)
                        waiting.remove(provider)
                    if not waiting:
                        return tuple(connected)
                    next(iter(pages.values())).wait_for_timeout(1000)
                raise CampusError(
                    Code.AUTH_REQUIRED, "Campus sign-in timed out; completed logins saved."
                )
            finally:
                browser.close()
    except BrowserError:
        raise CampusError(
            Code.AUTH_REQUIRED,
            "Chrome closed or could not complete sign-in; completed logins saved.",
        ) from None


def existing_account(candidate: Account) -> Account:
    """Keep approved scopes only when provider, instance and principal match exactly."""
    return next(
        (account for account in preferences().accounts if account.id == candidate.id), candidate
    )
