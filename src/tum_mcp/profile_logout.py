from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, sync_playwright

from tum_mcp.browser_profiles import browser_choices
from tum_mcp.connect import SERVICE_ORIGINS, ServiceChoice
from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import discover_browsers
from tum_mcp.profile_session import login_context


def clear_campus_signins(context: BrowserContext, services: tuple[ServiceChoice, ...]) -> None:
    origins = tuple(SERVICE_ORIGINS[service].split("/tumonline/")[0] for service in services)
    origins += ("https://login.tum.de", "https://idp.tum.de", "https://tum.de")
    hosts = {urlsplit(origin).hostname for origin in origins}
    if ServiceChoice.MOODLE in services:
        hosts.add("moodle.tum.de")
        origins += ("https://moodle.tum.de",)
    for cookie in context.cookies():
        if cookie["domain"].lstrip(".") in hosts:
            context.clear_cookies(name=cookie["name"], domain=cookie["domain"], path=cookie["path"])
    page = context.new_page()
    session = context.new_cdp_session(page)
    try:
        for origin in origins:
            session.send("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "all"})
    finally:
        session.detach()
        page.close()


def clear_saved_signins(services: tuple[ServiceChoice, ...]) -> None:
    for browser in browser_choices(discover_browsers()):
        if browser.profile is not None:
            with browser_driver(browser), sync_playwright() as driver:
                with login_context(driver.chromium, browser) as context:
                    clear_campus_signins(context, services)
