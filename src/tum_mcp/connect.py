"""Explicit local onboarding; credential values never pass through MCP arguments."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never
from urllib.parse import urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import Page, sync_playwright
from pydantic import SecretStr

from tum_mcp.artemis.models import Identity as ArtemisIdentity
from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import Cookie, LoginProgress, Session, SessionStore
from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError, discover_browsers
from tum_mcp.moodle.config import BASE_URL, Paths
from tum_mcp.parsing import decode
from tum_mcp.settings import ARTEMIS, TUM_LIVE, ZULIP, Account, Provider, preferences, save_account
from tum_mcp.transport import API, MAX_RESPONSE
from tum_mcp.tum_live.wire import Identity as LiveIdentity
from tum_mcp.zulip.models import Identity as ZulipIdentity


def connect_zulip(email: str, key: SecretStr) -> Account:
    pending = Account(provider=Provider.ZULIP, origin=ZULIP, principal="pending")
    credential = Credential(account_id=pending.id, username=SecretStr(email), api_key=key)
    identity = decode(ZulipIdentity, API(pending, credential).get("/api/v1/users/me"))
    account = existing_account(pending.model_copy(update={"principal": str(identity.user_id)}))
    Vault().replace_login(account, credential.model_copy(update={"account_id": account.id}))
    save_account(account, preserve_settings=True)
    return account


def connect_artemis() -> Account:
    return connect_browser((Provider.ARTEMIS,))[0]


class ServiceChoice(StrEnum):
    MOODLE = "moodle"
    ARTEMIS = "artemis"
    ZULIP = "zulip"
    TUM_LIVE = "tum_live"

    @property
    def label(self) -> str:
        return {
            ServiceChoice.MOODLE: "Moodle",
            ServiceChoice.ARTEMIS: "Artemis",
            ServiceChoice.ZULIP: "Zulip",
            ServiceChoice.TUM_LIVE: "TUM-Live",
        }[self]


def available_services() -> tuple[ServiceChoice, ...]:
    from tum_mcp.extensions import lecture_enabled

    return tuple(
        service
        for service in ServiceChoice
        if service != ServiceChoice.TUM_LIVE or lecture_enabled()
    )


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    service: ServiceChoice
    account: Account | None = None


def connect_browser(providers: tuple[Provider, ...]) -> tuple[Account, ...]:
    results = connect_services(tuple(ServiceChoice(provider.value) for provider in providers))
    return tuple(result.account for result in results if result.account is not None)


def connect_services(
    services: tuple[ServiceChoice, ...],
    on_connected: Callable[[ConnectionResult], None] | None = None,
    *,
    browser: BrowserChoice | None = None,
) -> tuple[ConnectionResult, ...]:
    """Open only selected services in one temporary context, without native-store access."""
    if not services or len(set(services)) != len(services):
        raise CampusError(Code.SCOPE_DENIED, "Select each service exactly once.")
    if ServiceChoice.TUM_LIVE in services:
        from tum_mcp.extensions import require_lecture

        require_lecture()
    available = (browser,) if browser is not None else discover_browsers()
    if not available:
        raise BrowserSetupError("Install a Chromium browser, then run tum-mcp connect.")
    selected_browser = available[0]
    origins = {
        ServiceChoice.MOODLE: BASE_URL,
        ServiceChoice.ARTEMIS: ARTEMIS,
        ServiceChoice.ZULIP: ZULIP,
        ServiceChoice.TUM_LIVE: TUM_LIVE,
    }
    connected: dict[ServiceChoice, ConnectionResult] = {}
    try:
        with browser_driver(selected_browser), sync_playwright() as playwright:
            instance = playwright.chromium.launch(
                executable_path=selected_browser.executable, headless=False
            )
            try:
                context = instance.new_context()
                pages: dict[ServiceChoice, Page] = {}
                for service in services:
                    page = context.new_page()
                    page.goto(origins[service], wait_until="domcontentloaded")
                    pages[service] = page
                deadline = time.monotonic() + 600
                while time.monotonic() < deadline:
                    for service in services:
                        if service in connected:
                            continue
                        origin = origins[service]
                        identity_path = {
                            ServiceChoice.MOODLE: "/my/courses.php",
                            ServiceChoice.ARTEMIS: "/api/core/public/account",
                            ServiceChoice.ZULIP: "/json/users/me",
                            ServiceChoice.TUM_LIVE: "/api/v2/users/me",
                        }[service]
                        response = context.request.get(
                            origin + identity_path, max_redirects=0, timeout=10000
                        )
                        if response.status != 200:
                            continue
                        payload = response.body()
                        if len(payload) > MAX_RESPONSE:
                            raise CampusError(
                                Code.INVALID_RESPONSE, "Identity response exceeded budget."
                            )
                        if service == ServiceChoice.MOODLE and b"logout.php" not in payload:
                            continue
                        if (
                            service == ServiceChoice.TUM_LIVE
                            and decode(LiveIdentity, payload).user is None
                        ):
                            continue
                        allowed_hosts = {urlsplit(origin).hostname}
                        if service == ServiceChoice.MOODLE:
                            allowed_hosts.add("moodle.tum.de")
                        cookies = tuple(
                            Cookie.model_validate(item)
                            for item in context.cookies(origin)
                            if item["domain"].lstrip(".") in allowed_hosts
                        )
                        if not cookies:
                            raise CampusError(
                                Code.AUTH_REQUIRED,
                                "No service-owned session cookie was established.",
                            )
                        result = _save_connection(service, payload, cookies)
                        connected[service] = result
                        if on_connected:
                            on_connected(result)
                    if len(connected) == len(services):
                        return tuple(connected[service] for service in services)
                    next(iter(pages.values())).wait_for_timeout(1000)
                raise CampusError(
                    Code.AUTH_REQUIRED, "Sign-in timed out; completed connections were saved."
                )
            finally:
                instance.close()
    except BrowserError:
        raise CampusError(
            Code.AUTH_REQUIRED,
            "The browser closed or could not complete sign-in. Completed connections were saved; "
            "run tum-mcp connect to retry or choose another browser.",
        ) from None


def _save_connection(
    service: ServiceChoice, payload: bytes, cookies: tuple[Cookie, ...]
) -> ConnectionResult:
    if service == ServiceChoice.MOODLE:
        store = SessionStore(Paths.default(), storage="file")
        generation = store.begin_login()
        store.save(Session(generation=generation, cookies=list(cookies), verified_at=time.time()))
        store.set_progress(
            LoginProgress(operation_id=generation, state="connected", started_at=time.time())
        )
        return ConnectionResult(service)
    provider = Provider(service.value)
    origin = {Provider.ARTEMIS: ARTEMIS, Provider.ZULIP: ZULIP, Provider.TUM_LIVE: TUM_LIVE}[
        provider
    ]
    principal = _principal(provider, payload)
    account = existing_account(Account(provider=provider, origin=origin, principal=principal))
    credential = Credential(
        account_id=account.id, authentication="browser_session", cookies=cookies
    )
    path = {
        Provider.ARTEMIS: "/api/core/public/account",
        Provider.ZULIP: "/api/v1/users/me",
        Provider.TUM_LIVE: "/api/v2/users/me",
    }[provider]
    verification = API(account, credential).get(path)
    verified = _principal(provider, verification)
    if verified != principal:
        raise CampusError(Code.SCOPE_DENIED, "Identity changed during connection.")
    Vault().replace_login(account, credential)
    save_account(account, preserve_settings=True)
    return ConnectionResult(service, account)


def _principal(provider: Provider, payload: bytes) -> str:
    match provider:
        case Provider.ARTEMIS:
            return str(decode(ArtemisIdentity, payload).id)
        case Provider.ZULIP:
            return str(decode(ZulipIdentity, payload).user_id)
        case Provider.TUM_LIVE:
            identity = decode(LiveIdentity, payload)
            if identity.user is None:
                raise CampusError(Code.AUTH_REQUIRED, "Complete TUM-Live sign-in.")
            return str(identity.user.id)
        case unreachable:
            assert_never(unreachable)


def existing_account(candidate: Account) -> Account:
    """Keep saved preferences only when provider, instance and principal match exactly."""
    return next(
        (account for account in preferences().accounts if account.id == candidate.id), candidate
    )
