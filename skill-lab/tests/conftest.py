import pytest


@pytest.fixture
def lab_state(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("SKILL_LAB_STATE", str(state))
    monkeypatch.setenv("SKILL_LAB_WORKSPACES", str(tmp_path / "workspaces"))
    return state
