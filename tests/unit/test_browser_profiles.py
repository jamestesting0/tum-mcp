import json
import shutil
from dataclasses import replace
from pathlib import Path, PureWindowsPath

import pytest
from filelock import Timeout

from tum_mcp import browser_profiles as profiles
from tum_mcp import profile_paths
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError, WindowsHost


def existing(root: Path, names: tuple[str, ...] = ("Work", "Study")) -> None:
    root.mkdir(parents=True)
    cache = {}
    for index, name in enumerate(names):
        directory = f"Profile {index + 1}"
        (root / directory).mkdir()
        (root / directory / "Preferences").write_text("{}", encoding="utf-8")
        cache[directory] = {"name": name, "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_0"}
    (root / "Local State").write_text(
        json.dumps(
            {
                "browser": {"enabled_labs_experiments": []},
                "profile": {"info_cache": cache, "last_used": "Profile 1"},
            }
        )
    )


def test_existing_profile_registration_preserves_data_and_remembers_exact_profile(
    tmp_path: Path,
) -> None:
    chrome = BrowserChoice("Chrome", "chrome")
    edge = BrowserChoice("Edge", "edge")
    root = tmp_path / "dedicated"
    existing(root)
    before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    found = profiles.profiles_in(chrome, str(root))
    assert [(item.name, item.directory) for item in found] == [
        ("Work", "Profile 1"),
        ("Study", "Profile 2"),
    ]
    saved = profiles.register_profile(replace(chrome, profile=found[1]))
    profiles.register_profile(replace(chrome, profile=found[0]))
    profiles.remember_browser(saved)
    assert profiles.browser_choices((chrome, edge))[0] == saved
    assert profiles.register_profile(replace(chrome, profile=found[1])) == saved
    assert len(profiles.read_preferences().profiles) == 2
    profiles.rename_profile(saved, "University")
    assert profiles.browser_choices((chrome, edge))[0].profile.name == "University"
    profiles.remove_profile(saved)
    assert {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    } == before
    assert profiles.browser_choices((chrome, edge))[0] == chrome
    profiles.remember_browser(edge)
    assert profiles.browser_choices((chrome, edge))[0] == edge
    assert profiles.browser_choices((chrome,)) == (chrome, replace(chrome, profile=found[0]))


def test_missing_profile_falls_back_and_managed_removal_never_deletes_imported_data(
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
    external = tmp_path / "external"
    existing(external)
    imported = profiles.register_profile(
        replace(browser, profile=profiles.profiles_in(browser, str(external))[0])
    )
    profiles.remember_browser(imported)
    shutil.rmtree(external / "Profile 1")
    assert profiles.browser_choices((browser,)) == (browser,)


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux", "wsl1", "wsl2"])
def test_profiles_use_the_browser_host_paths_and_reject_everyday_roots(
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
    for root in profile_paths.everyday_roots(browser):
        existing(root)
        with pytest.raises(BrowserSetupError, match="Everyday"):
            profiles.profiles_in(browser, str(root / "Profile 1"))
    root = tmp_path / "automation"
    existing(root)
    assert len(profiles.profiles_in(browser, str(root))) == 2


@pytest.mark.parametrize(
    "contents", ["broken json", '{"profile":{"info_cache":{"../escape":{"name":"Bad"}}}}']
)
def test_untrusted_metadata_cannot_register_a_profile(
    tmp_path: Path,
    contents: str,
) -> None:
    root = tmp_path / "custom"
    root.mkdir()
    (root / "Local State").write_text(contents, encoding="utf-8")
    with pytest.raises(BrowserSetupError):
        profiles.profiles_in(BrowserChoice("Chrome", "chrome"), str(root))
    assert profiles.read_preferences().profiles == ()


@pytest.mark.parametrize("import_existing", [False, True])
def test_login_setup_creates_or_imports_the_selected_browser_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    import_existing: bool,
) -> None:
    from tum_mcp.commands import browser_profiles as command
    from tum_mcp.commands import choices, ui

    browsers = (BrowserChoice("Chrome", "chrome"), BrowserChoice("Edge", "edge"))
    root = tmp_path / "existing"
    existing(root)
    answers = iter(("3", "2", "2", "1", str(root), "2") if import_existing else ("3", "1", "2", ""))
    monkeypatch.setenv("TERM", "dumb")
    for module in (command, choices, ui):
        monkeypatch.setattr(module, "numbered_input", lambda prompt: next(answers))
    selected = command.choose_login_browser(browsers)
    assert selected.executable == "edge"
    assert selected.profile.managed is not import_existing
    assert selected.profile.directory == ("Profile 2" if import_existing else "Default")
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


def test_managed_ownership_cannot_be_claimed_for_an_external_profile(tmp_path: Path) -> None:
    browser = BrowserChoice("Chrome", "chrome")
    root = tmp_path / "external"
    existing(root)
    profile = profiles.profiles_in(browser, str(root))[0].model_copy(update={"managed": True})
    with pytest.raises(BrowserSetupError, match="ownership"):
        profiles.remove_profile(replace(browser, profile=profile))
    assert (root / "Profile 1/Preferences").read_text(encoding="utf-8") == "{}"
