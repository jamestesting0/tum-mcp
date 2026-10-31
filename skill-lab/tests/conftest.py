import sys
from pathlib import Path

import pytest


def pytest_collection_modifyitems(items):
    if sys.platform != "win32":
        return
    here = Path(__file__).parent
    skip = pytest.mark.skip(reason="The skill lab isolates hosts by POSIX HOME; macOS and Linux.")
    for item in items:
        if here in item.path.parents:
            item.add_marker(skip)


@pytest.fixture
def lab_state(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("SKILL_LAB_STATE", str(state))
    monkeypatch.setenv("SKILL_LAB_WORKSPACES", str(tmp_path / "workspaces"))
    return state
