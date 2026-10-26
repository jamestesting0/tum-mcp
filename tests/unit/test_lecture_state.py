import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.settings import (
    Account,
    CourseMapping,
    Preferences,
    Provider,
    preferences,
    save_account,
)
from tum_mcp.study_models import Snapshot


def test_legacy_state_keeps_version_and_live_state_requires_new_version() -> None:
    path = Path(__file__).parents[1] / "fixtures/course_app/snapshot.json"
    original = json.loads(path.read_bytes())
    snapshot = Snapshot.model_validate(original)
    assert snapshot.schema_version == 1
    assert snapshot.model_dump(mode="json", exclude_none=True)["course"] == original["course"]
    original["course"]["synthetic"] = False
    original["course"]["bindings"][0]["provider"] = "tum_live"
    original["course"]["bindings"][0]["course_id"] = "2464"
    original["course"]["bindings"][0]["course_slug"] = "950943622"
    with pytest.raises(ValidationError):
        Snapshot.model_validate(original)
    original["schema_version"] = 2
    assert Snapshot.model_validate(original).schema_version == 2


def test_saving_live_account_upgrades_preferences_without_resetting_existing_settings(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    old = Account(provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7")
    save_account(old)
    assert preferences().schema_version == 1
    live = Account(provider=Provider.TUM_LIVE, origin="https://live.rbg.tum.de", principal="8")
    save_account(live)
    assert preferences().schema_version == 2
    assert preferences().accounts[0].id == old.id
    assert preferences().accounts[1].id == live.id
    with pytest.raises(ValidationError):
        Preferences.model_validate({"schema_version": 3})


def test_old_settings_do_not_emit_new_provider_fields_with_an_old_version() -> None:
    before = Preferences(mappings=(CourseMapping(name="Existing", moodle_id=42),))
    mapping = before.model_dump(mode="json")["mappings"][0]
    assert before.schema_version == 1
    assert not any(key.startswith("tum_live") for key in mapping)
