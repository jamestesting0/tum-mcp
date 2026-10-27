import json
import subprocess
from pathlib import Path

import pytest

from tum_mcp.connect import ServiceChoice, available_services, connect_services
from tum_mcp.errors import CampusError, Code
from tum_mcp.studocu.connection import open_browser


@pytest.fixture(autouse=True)
def isolated_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def test_optional_providers_appear_only_after_installation(tmp_path: Path) -> None:
    assert not {ServiceChoice.STUDOCU, ServiceChoice.TUM_LIVE} & set(available_services())
    (tmp_path / "extensions.json").write_text('{"schema_version":1,"studocu":true}')
    (tmp_path / "lecture-extension.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "enabled": True,
                "installed_at": "2026-10-27T00:00:00Z",
                "package_version": "fixture",
                "asr_requested": False,
            }
        )
    )
    assert {ServiceChoice.STUDOCU, ServiceChoice.TUM_LIVE} <= set(available_services())


def test_browser_only_studocu_never_claims_verified_auth_or_starts_a_campus_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "extensions.json").write_text('{"schema_version":1,"studocu":true}')
    opened = []
    reported = []
    monkeypatch.setattr("tum_mcp.studocu.connection.is_wsl", lambda: False)
    monkeypatch.setattr("webbrowser.open_new_tab", lambda url: opened.append(url) or True)
    monkeypatch.setattr(
        "tum_mcp.connect._connect_campus_services", lambda *a, **k: pytest.fail("No campus browser")
    )
    result = connect_services((ServiceChoice.STUDOCU,), reported.append)
    assert opened == ["https://www.studocu.com/"]
    assert result == tuple(reported)
    assert result[0].verified is False and result[0].account is None


def test_disabled_studocu_cannot_open_a_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("webbrowser.open_new_tab", lambda url: pytest.fail("No browser"))
    with pytest.raises(CampusError):
        connect_services((ServiceChoice.STUDOCU,))


def test_browser_failure_is_actionable_without_claiming_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tum_mcp.studocu.connection.is_wsl", lambda: False)
    monkeypatch.setattr("webbrowser.open_new_tab", lambda url: False)
    with pytest.raises(CampusError) as error:
        open_browser()
    assert error.value.code == Code.ACTION_REQUIRED


def test_wsl_opens_the_windows_default_browser_without_a_shell_or_session_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr("tum_mcp.studocu.connection.is_wsl", lambda: True)
    monkeypatch.setattr("shutil.which", lambda name: "synthetic-powershell.exe")

    def run(args: list[str], **kwargs: int) -> subprocess.CompletedProcess:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("webbrowser.open_new_tab", lambda url: pytest.fail("Use Windows browser"))
    open_browser()
    assert calls == [
        [
            "synthetic-powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Start-Process",
            "https://www.studocu.com/",
        ]
    ]
