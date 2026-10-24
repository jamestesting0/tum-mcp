import os
from pathlib import Path, PureWindowsPath

import pytest

from tum_moodle import browsers
from tum_moodle.browsers import BrowserSetupError, WindowsHost


def test_linux_discovery_supports_multiple_chromium_browsers_without_launching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executables = {}
    for command in ("brave-browser", "microsoft-edge", "chromium", "vivaldi", "opera"):
        path = tmp_path / command
        path.write_text("not executed")
        path.chmod(0o700)
        executables[command] = str(path)
    monkeypatch.setattr(browsers.sys, "platform", "linux")
    monkeypatch.setattr(browsers, "is_wsl", lambda: False)
    monkeypatch.delenv("TUM_MCP_BROWSER", raising=False)
    monkeypatch.setattr(browsers.shutil, "which", executables.get)
    result = browsers.discover_browsers()
    assert {browser.name for browser in result} == {
        "Brave",
        "Microsoft Edge",
        "Chromium",
        "Vivaldi",
        "Opera",
    }
    assert all(not browser.windows_host for browser in result)


def test_wsl_discovers_windows_edge_and_brave_on_a_nonstandard_drive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    windows_root = PureWindowsPath("D:/Windows apps")
    for suffix in (
        "Microsoft/Edge/Application/msedge.exe",
        "BraveSoftware/Brave-Browser/Application/brave.exe",
    ):
        path = tmp_path / suffix
        path.parent.mkdir(parents=True)
        path.write_bytes(b"synthetic-not-executed")
    monkeypatch.setattr(browsers.sys, "platform", "linux")
    monkeypatch.setattr(browsers, "is_wsl", lambda: True)
    monkeypatch.delenv("TUM_MCP_BROWSER", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(
        browsers, "windows_host", lambda: WindowsHost(windows_root, windows_root, (), "x64")
    )
    monkeypatch.setattr(browsers, "wsl_path", lambda path: str(tmp_path))
    result = browsers.discover_browsers()
    assert {browser.name for browser in result} == {"Microsoft Edge", "Brave"}
    assert all(browser.windows_host and browser.executable.startswith("D:\\") for browser in result)


def test_explicit_custom_browser_is_validated_without_executing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "custom Chromium"
    path.write_text("not executed")
    path.chmod(0o700)
    monkeypatch.setenv("TUM_MCP_BROWSER", str(path))
    monkeypatch.setattr(browsers, "is_wsl", lambda: False)
    assert browsers.discover_browsers()[0].executable == str(path.resolve())
    monkeypatch.setenv("TUM_MCP_BROWSER", str(tmp_path / "missing"))
    with pytest.raises(BrowserSetupError, match="executable Chromium"):
        browsers.discover_browsers()


def test_wsl_detection_does_not_treat_native_windows_as_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", "Synthetic Ubuntu")
    monkeypatch.setattr(browsers.sys, "platform", "win32")
    assert not browsers.is_wsl()
    monkeypatch.setattr(browsers.sys, "platform", "linux")
    assert browsers.is_wsl()


def test_browser_discovery_has_no_native_store_or_browser_process_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TUM_MCP_BROWSER", raising=False)
    monkeypatch.setattr(browsers.sys, "platform", "linux")
    monkeypatch.setattr(browsers, "is_wsl", lambda: False)
    monkeypatch.setattr(browsers.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        browsers.subprocess, "run", lambda *args, **kwargs: pytest.fail("No process expected")
    )
    before = dict(os.environ)
    assert browsers.discover_browsers() == ()
    assert dict(os.environ) == before
