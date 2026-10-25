from pathlib import Path

import pytest

from tum_mcp.moodle import platforms
from tum_mcp.moodle.platforms import System


@pytest.mark.parametrize(
    "case",
    [
        (System.MACOS, "Library/Application Support/TUMMoodle"),
        (System.WINDOWS, "AppData/Local/TUMMoodle"),
        (System.LINUX, ".local/share/TUMMoodle"),
    ],
)
def test_default_storage_follows_the_desktop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: tuple[System, str]
) -> None:
    desktop, relative = case
    for name in ("TUM_MOODLE_DATA_DIR", "LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(platforms, "system", lambda: desktop)

    assert platforms.data_root() == tmp_path / relative


@pytest.mark.parametrize(
    "case",
    [(System.WINDOWS, "LOCALAPPDATA"), (System.LINUX, "XDG_DATA_HOME")],
)
def test_storage_respects_the_user_data_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: tuple[System, str]
) -> None:
    desktop, variable = case
    monkeypatch.delenv("TUM_MOODLE_DATA_DIR", raising=False)
    monkeypatch.setattr(platforms, "system", lambda: desktop)
    monkeypatch.setenv(variable, str(tmp_path))

    assert platforms.data_root() == tmp_path / "TUMMoodle"


@pytest.mark.parametrize("desktop", list(System))
def test_runtime_stays_installed_when_the_session_location_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, desktop: System
) -> None:
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(platforms, "system", lambda: desktop)
    monkeypatch.setattr(platforms, "app_root", lambda: tmp_path / "app")

    expected = "Scripts/python.exe" if desktop is System.WINDOWS else "bin/python"
    assert platforms.data_root() == tmp_path
    assert platforms.runtime_python() == tmp_path / "app/runtime" / expected
