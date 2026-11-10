import shutil
from dataclasses import replace
from pathlib import Path, PureWindowsPath

import pytest
from filelock import Timeout

from tum_mcp import browser_profiles as profiles
from tum_mcp import profile_paths
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError, WindowsHost


def test_saved_profile_management_remembers_the_exact_profile(
    tmp_path: Path,
) -> None:
    chrome = BrowserChoice("Chrome", "chrome")
    edge = BrowserChoice("Edge", "edge")
    other = profiles.create_profile(chrome, "Work")
    saved = profiles.create_profile(chrome, "Study")
    profiles.remember_browser(saved)
    assert profiles.browser_choices((chrome, edge))[0] == saved
    assert len(profiles.read_preferences().profiles) == 2
    profiles.rename_profile(saved, "University")
    assert profiles.browser_choices((chrome, edge))[0].profile.name == "University"
    assert profiles.browser_choices((chrome, edge))[0].login_label == "Chrome (University)"
    profiles.remove_profile(saved)
    assert not Path(saved.profile.root).exists()
    assert Path(other.profile.root).is_dir()
    assert profiles.browser_choices((chrome, edge))[0] == chrome
    profiles.remember_browser(edge)
    assert profiles.browser_choices((chrome, edge))[0] == edge
    assert profiles.browser_choices((chrome,)) == (chrome, other)


def test_missing_profile_falls_back_and_in_use_profiles_cannot_be_removed(
    tmp_path: Path,
) -> None:
    browser = BrowserChoice("Chrome", "chrome")
    saved = profiles.create_profile(browser, "Study")
    root = Path(saved.profile.root)
    profiles.remember_browser(saved)
    assert profiles.browser_choices((browser,))[0] == saved
    with profiles.profile_lock(saved), pytest.raises(Timeout):
        profiles.remove_profile(saved)
    assert root.is_dir()
    profiles.remove_profile(saved)
    assert not root.exists() and profiles.read_preferences().profiles == ()
    saved = profiles.create_profile(browser, "Missing")
    profiles.remember_browser(saved)
    shutil.rmtree(saved.profile.root)
    assert profiles.browser_choices((browser,)) == (browser,)


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux", "wsl1", "wsl2"])
def test_profiles_use_the_browser_host_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
) -> None:
    windows = platform.startswith("wsl")
    browser = BrowserChoice("Chrome", "D:\\Apps\\chrome.exe" if windows else "chrome", windows)
    monkeypatch.setattr(profile_paths.sys, "platform", "linux" if windows else platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("CHROME_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CHROME_USER_DATA_DIR", raising=False)
    host = WindowsHost(
        PureWindowsPath("D:/Users/Synthetic"), PureWindowsPath("D:/Local"), (), "x64"
    )
    monkeypatch.setattr(profile_paths, "windows_host", lambda: host)

    def translate(path: str, *, windows: bool = False) -> str:
        if windows:
            return str(PureWindowsPath("D:/") / Path(path).relative_to(tmp_path).as_posix())
        return str(tmp_path / PureWindowsPath(path).relative_to("D:/").as_posix())

    monkeypatch.setattr(profile_paths, "wsl_path", translate)
    if windows:
        assert profile_paths.managed_root(browser).is_relative_to(
            tmp_path / "Local/TUMMCP/browser-profiles"
        )
        assert (
            profile_paths.launch_path(browser, tmp_path / "Local/Profile") == "D:\\Local\\Profile"
        )
        assert profile_paths.local_path(browser, "D:\\Local\\Profile") == tmp_path / "Local/Profile"
    else:
        from tum_mcp.settings import data_path

        assert profile_paths.managed_root(browser).is_relative_to(data_path() / "browser-profiles")


def test_login_setup_creates_the_selected_browser_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tum_mcp.commands import browser_profiles as command
    from tum_mcp.commands import choices, ui

    browsers = (BrowserChoice("Chrome", "chrome"), BrowserChoice("Edge", "edge"))
    answers = iter(("3", "2", ""))
    monkeypatch.setenv("TERM", "dumb")
    for module in (command, choices, ui):
        monkeypatch.setattr(module, "numbered_input", lambda prompt: next(answers))
    selected = command.choose_login_browser(browsers)
    assert selected.executable == "edge"
    assert Path(selected.profile.root).is_dir()
    assert profiles.browser_choices(browsers)[0] == selected


def test_damaged_profile_session_is_reported_without_overwriting_it() -> None:
    from unittest.mock import MagicMock

    from tum_mcp.moodle.secret_files import local_cipher
    from tum_mcp.profile_cookies import cookie_file
    from tum_mcp.profile_session import login_context

    saved = profiles.create_profile(BrowserChoice("Chrome", "chrome"), "Study")
    path = cookie_file(saved.profile)
    local_cipher(path.parent, create=True)
    path.write_bytes(b"damaged-synthetic-session")
    with pytest.raises(BrowserSetupError, match="unreadable"):
        with login_context(MagicMock(), saved, headless=True):
            pytest.fail("Unreadable sessions must fail before login proceeds.")
    assert path.read_bytes() == b"damaged-synthetic-session"


def test_profile_ownership_cannot_be_redirected_to_an_external_directory(tmp_path: Path) -> None:
    browser = BrowserChoice("Chrome", "chrome")
    root = tmp_path / "external"
    root.mkdir()
    (root / "keep.txt").write_text("unrelated data", encoding="utf-8")
    saved = profiles.create_profile(browser, "Study")
    profile = saved.profile.model_copy(update={"root": str(root)})
    with pytest.raises(BrowserSetupError, match="ownership"):
        profiles.remove_profile(replace(browser, profile=profile))
    assert (root / "keep.txt").read_text(encoding="utf-8") == "unrelated data"


@pytest.mark.parametrize(
    "windows_path", [r"D:\Profiles\Synthetic User", r"\\synthetic-host\profiles\Study"]
)
def test_wsl_persistent_profile_path_survives_python_and_windows_node_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    windows_path: str,
) -> None:
    import os
    import subprocess
    from unittest.mock import AsyncMock

    import playwright
    from playwright.sync_api import Error, sync_playwright

    from tum_mcp import profile_session

    profile = profiles.BrowserProfile(
        id="a" * 32, executable="unused", root=windows_path, name="Synthetic"
    )
    browser = BrowserChoice("Windows browser", "unused", True, profile)
    root = tmp_path / profile.id
    root.mkdir()
    monkeypatch.setattr(profile_paths, "managed_root", lambda _: tmp_path)
    monkeypatch.setattr(profile_paths, "local_path", lambda *_: root)
    monkeypatch.setattr(profile_session, "protect_directory", lambda *_: None)
    probe = AsyncMock(side_effect=Error("Synthetic protocol capture; no browser is launched."))
    with sync_playwright() as driver:
        monkeypatch.setattr(driver.chromium._impl_obj._channel, "send_return_as_dict", probe)
        with pytest.raises(BrowserSetupError):
            with profile_session.login_context(driver.chromium, browser, headless=True):
                pytest.fail("The synthetic protocol capture must stop before launch.")
    transmitted = probe.call_args.args[2]["userDataDir"]
    node = Path(playwright.__file__).parent / "driver" / ("node.exe" if os.name == "nt" else "node")
    result = subprocess.run(  # noqa: S603
        [
            str(node),
            "--eval",
            "process.stdout.write(require('node:path').win32.resolve(process.argv[1]))",
            transmitted,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    resolved = result.stdout.replace("\\\\?\\UNC\\", "\\\\", 1).removeprefix("\\\\?\\")
    assert PureWindowsPath(resolved) == PureWindowsPath(windows_path)
