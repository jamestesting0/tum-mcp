from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from cryptography.fernet import InvalidToken
from playwright.sync_api import BrowserContext
from playwright.sync_api import Cookie as BrowserCookie
from pydantic import ValidationError

from tum_mcp.moodle.auth import Cookie
from tum_mcp.moodle.browsers import BrowserSetupError
from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.secret_files import local_cipher, secure_directory
from tum_mcp.settings import Frozen, data_path

if TYPE_CHECKING:
    from tum_mcp.browser_profiles import BrowserProfile

CAMPUS_DOMAINS: Final = {
    "tum.de",
    "login.tum.de",
    "idp.tum.de",
    "moodle.tum.de",
    "www.moodle.tum.de",
    "artemis.tum.de",
    "zulip.cit.tum.de",
    "campus.tum.de",
    "live.rbg.tum.de",
}


class ProfileCookies(Frozen):
    root: str
    directory: str
    cookies: tuple[Cookie, ...]


def cookie_file(profile: BrowserProfile) -> Path:
    return data_path() / "credentials/browser-profiles" / f"{profile.id}.enc"


def restore_cookies(context: BrowserContext, profile: BrowserProfile) -> None:
    path = cookie_file(profile)
    if not path.exists():
        return
    if path.is_symlink():
        raise BrowserSetupError("Saved profile session cannot be a symbolic link.")
    try:
        saved = ProfileCookies.model_validate_json(
            local_cipher(path.parent, create=False).decrypt(path.read_bytes())
        )
    except (OSError, InvalidToken, ValidationError):
        raise BrowserSetupError(
            "Saved profile session is unreadable. Remove and recreate this saved profile."
        ) from None
    if saved.root != profile.root or saved.directory != profile.directory:
        raise BrowserSetupError("Saved profile location changed. Add it again.")
    current = {(item["name"], item["domain"], item["path"]) for item in context.cookies()}
    cookies: list[BrowserCookie] = []
    for item in saved.cookies:
        if (item.name, item.domain, item.path) in current:
            continue
        cookies.append(
            BrowserCookie(
                name=item.name,
                value=item.value,
                domain=item.domain,
                path=item.path,
                expires=item.expires,
                httpOnly=item.httpOnly,
                secure=item.secure,
                sameSite=item.sameSite,
            )
        )
    context.add_cookies(cookies)


def retain_cookies(context: BrowserContext, profile: BrowserProfile) -> None:
    cookies = tuple(
        Cookie.model_validate(item)
        for item in context.cookies()
        if item["domain"].lstrip(".") in CAMPUS_DOMAINS and not item.get("partitionKey")
    )
    path = cookie_file(profile)
    secure_directory(path.parent)
    cipher = local_cipher(path.parent, create=True)
    private_write(
        path,
        cipher.encrypt(
            ProfileCookies(root=profile.root, directory=profile.directory, cookies=cookies)
            .model_dump_json()
            .encode()
        ),
    )
