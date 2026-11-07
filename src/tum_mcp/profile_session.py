from collections.abc import Iterator
from contextlib import contextmanager, suppress

from filelock import Timeout
from playwright._impl._errors import TargetClosedError
from playwright.sync_api import BrowserContext, BrowserType, Error, sync_playwright

from tum_mcp.browser_profiles import profile_lock
from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError
from tum_mcp.profile_cookies import restore_cookies, retain_cookies
from tum_mcp.profile_paths import profile_root, protect_directory, windows_driver_path


@contextmanager
def login_context(
    engine: BrowserType, browser: BrowserChoice, *, headless: bool = False
) -> Iterator[BrowserContext]:
    profile = browser.profile
    if profile is None:
        instance = engine.launch(executable_path=browser.executable, headless=headless)
        try:
            yield instance.new_context()
        finally:
            instance.close()
        return
    root = profile_root(browser)
    if not root.is_dir():
        raise BrowserSetupError(
            "Saved browser profile is missing. Set it up again or use temporary."
        )
    try:
        with profile_lock(browser):
            protect_directory(browser, root)
            context = engine.launch_persistent_context(
                user_data_dir=windows_driver_path(profile.root)
                if browser.windows_host
                else profile.root,
                executable_path=browser.executable,
                headless=headless,
                args=[f"--profile-directory={profile.directory}"],
                ignore_default_args=[
                    "--enable-automation",
                    "--password-store=basic",
                    "--use-mock-keychain",
                ],
            )
            try:
                restore_cookies(context, profile)
                try:
                    yield context
                finally:
                    with suppress(TargetClosedError):
                        if context.browser is not None and context.browser.is_connected():
                            retain_cookies(context, profile)
            finally:
                with suppress(TargetClosedError):
                    context.close()
    except Timeout:
        raise BrowserSetupError("Saved browser profile is in use. Close it and retry.") from None
    except Error:
        raise BrowserSetupError(
            "Saved browser could not complete login. Close other windows using this profile "
            "and retry."
        ) from None


def open_profile(browser: BrowserChoice) -> None:
    if browser.profile is None:
        raise BrowserSetupError("Choose a saved profile to open.")
    with browser_driver(browser), sync_playwright() as driver:
        with login_context(driver.chromium, browser) as context:
            if not context.pages:
                context.new_page()
            while context.pages:
                context.pages[0].wait_for_event("close", timeout=0)
