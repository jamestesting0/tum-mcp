import json
from pathlib import Path

import pytest

from tum_mcp.connect import ServiceChoice, available_services


@pytest.fixture(autouse=True)
def isolated_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def test_optional_providers_appear_only_after_installation(tmp_path: Path) -> None:
    assert ServiceChoice.TUM_LIVE not in available_services()
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
    assert ServiceChoice.TUM_LIVE in available_services()
