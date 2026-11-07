import sys
from enum import Enum

import typer
from filelock import Timeout
from pydantic import ValidationError

from tum_mcp.browser_profiles import (
    browser_choices,
    create_profile,
    read_preferences,
    remember_browser,
    remove_profile,
    rename_profile,
)
from tum_mcp.commands.choices import choose
from tum_mcp.commands.terminal_input import numbered_input
from tum_mcp.commands.ui import heading, select_browser, terminal_console
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError, discover_browsers


class Action(Enum):
    SETUP = "setup"
    RENAME = "rename"
    REMOVE = "remove"
    DONE = "done"


def choose_login_browser(browsers: tuple[BrowserChoice, ...]) -> BrowserChoice:
    if not browsers:
        return select_browser(browsers)
    entries: list[tuple[BrowserChoice | Action, str]] = list(
        (browser, browser.login_label) for browser in browser_choices(browsers)
    )
    entries.append((Action.SETUP, "Set up a saved profile…"))
    selected = choose("Choose browser", tuple(entries))
    match selected:
        case BrowserChoice():
            browser = selected
        case Action.SETUP:
            browser = setup_profile(browsers)
        case _:
            raise BrowserSetupError("Choose a browser or set up a saved profile.")
    remember_browser(browser)
    return browser


def profile_name(default: str) -> str:
    name = numbered_input(f"Profile name [{default}]: ").strip() or default
    if len(name) > 80:
        raise BrowserSetupError("Profile names must contain at most 80 characters.")
    return name


def setup_profile(browsers: tuple[BrowserChoice, ...]) -> BrowserChoice:
    last = read_preferences().last_browser
    browser = select_browser(tuple(sorted(browsers, key=lambda item: item.executable != last)))
    return create_profile(browser, profile_name(browser.name))


def manage_browsers() -> None:
    if not sys.stdin.isatty():
        raise CampusError(
            Code.ACTION_REQUIRED, "Run tum-mcp manage browsers in your interactive terminal."
        )
    console = terminal_console()
    heading(console, "Browsers", "Set up and manage saved browser profiles.")
    try:
        browsers = discover_browsers()
        while True:
            saved = tuple(item.browser for item in read_preferences().profiles)
            available = {item.profile.id for item in browser_choices(browsers) if item.profile}
            entries: list[tuple[BrowserChoice | Action, str]] = [
                (
                    item,
                    item.login_label
                    + (" - unavailable" if item.profile.id not in available else ""),
                )
                for item in saved
            ]
            entries.extend(((Action.SETUP, "Set up a saved profile…"), (Action.DONE, "Done")))
            selected = choose("Saved browsers", tuple(entries))
            match selected:
                case Action.DONE:
                    return
                case Action.SETUP:
                    if not browsers:
                        select_browser(browsers)
                    remember_browser(setup_profile(browsers))
                    console.print("Profile saved. Use tum-mcp login to sign in.")
                case BrowserChoice(profile=profile) if profile is not None:
                    action = choose(
                        profile.name, ((Action.RENAME, "Rename"), (Action.REMOVE, "Remove"))
                    )
                    if action == Action.RENAME:
                        rename_profile(selected, profile_name(profile.name))
                    else:
                        message = "Remove this profile and its saved browser data?"
                        if choose(message, ((False, "Cancel"), (True, "Remove"))):
                            remove_profile(selected)
                            console.print("Profile removed.")
                case _:
                    raise KeyboardInterrupt
    except (EOFError, KeyboardInterrupt):
        console.print("Cancelled.")
        raise typer.Exit(130) from None
    except Timeout:
        raise BrowserSetupError("Saved profile is in use. Close it and retry.") from None
    except ValidationError:
        raise BrowserSetupError("Profile settings are invalid.") from None
