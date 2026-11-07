from contextlib import ExitStack

from filelock import FileLock, Timeout

from tum_mcp.browser_profiles import (
    BrowserPreferences,
    profile_lock,
    read_preferences,
    remove_profile_data,
    write_preferences,
)
from tum_mcp.moodle.browsers import BrowserSetupError
from tum_mcp.moodle.secret_files import secure_directory
from tum_mcp.settings import config_dir, data_path


def forget_profiles() -> None:
    with FileLock(str(config_dir() / "browsers.lock")), ExitStack() as locks:
        profiles = read_preferences().profiles
        browsers = tuple(item.browser for item in profiles)
        locked_paths: set[str] = set()
        try:
            for browser in browsers:
                lock = profile_lock(browser)
                if lock.lock_file not in locked_paths:
                    locks.enter_context(lock)
                    locked_paths.add(lock.lock_file)
        except Timeout:
            raise BrowserSetupError(
                "A saved browser profile is in use. Close it before removing credentials."
            ) from None
        for browser in browsers:
            remove_profile_data(browser)
        root = data_path() / "credentials/browser-profiles"
        if root.exists():
            secure_directory(root)
            for file in root.glob("*.enc"):
                file.unlink()
            (root / "session.key").unlink(missing_ok=True)
        write_preferences(BrowserPreferences())
