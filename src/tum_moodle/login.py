import time

import anyio
from filelock import FileLock, Timeout
from playwright.async_api import Error as BrowserError
from playwright.async_api import async_playwright

from tum_moodle.auth import Cookie, LoginProgress, Session, SessionStore
from tum_moodle.config import BASE_URL, Paths
from tum_moodle.errors import ErrorCode, MoodleError


async def login(paths: Paths) -> None:
    store = SessionStore(paths)
    try:
        with FileLock(paths.file("login.lock"), timeout=0):
            await _login(store)
    except Timeout:
        raise MoodleError(ErrorCode.SETUP_REQUIRED, "A login window is already open.") from None


async def _login(store: SessionStore) -> None:
    generation = store.begin_login()
    started = time.time()
    progress = LoginProgress(operation_id=generation, state="authenticating", started_at=started)
    store.set_progress(progress)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=False)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(BASE_URL, wait_until="domcontentloaded")
                with anyio.fail_after(600):
                    while await page.locator('a[href*="/login/logout.php"]').count() == 0:
                        if store.generation() != generation:
                            raise MoodleError(ErrorCode.SESSION_EXPIRED, "Login was cancelled.")
                        await anyio.sleep(1)
                response = await context.request.get(f"{BASE_URL}/my/courses.php")
                if response.status != 200 or "logout.php" not in await response.text():
                    raise MoodleError(ErrorCode.AUTH_REQUIRED, "Could not verify Moodle sign-in.")
                cookies = [
                    Cookie.model_validate(cookie)
                    for cookie in await context.cookies(BASE_URL)
                    if cookie["domain"].lstrip(".") in {"moodle.tum.de", "www.moodle.tum.de"}
                ]
                if not cookies:
                    raise MoodleError(ErrorCode.AUTH_REQUIRED, "No Moodle session was established.")
                store.save(Session(generation=generation, cookies=cookies, verified_at=time.time()))
                store.set_progress(progress.model_copy(update={"state": "connected"}))
            finally:
                await browser.close()
    except (MoodleError, TimeoutError, BrowserError) as error:
        message = (
            error.message if isinstance(error, MoodleError) else "Login closed or timed out; retry."
        )
        store.set_progress(progress.model_copy(update={"state": "failed", "message": message}))
        raise MoodleError(ErrorCode.AUTH_REQUIRED, message) from None
