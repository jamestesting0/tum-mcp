from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest
from playwright.async_api import Error as BrowserError

from tum_moodle import login as login_module
from tum_moodle.auth import SessionStore
from tum_moodle.config import Paths
from tum_moodle.errors import MoodleError


@pytest.mark.parametrize(
    "scenario",
    [(BrowserError("internal browser details"), "Chrome"), (TimeoutError(), "timed out")],
)
def test_login_failure_is_actionable_and_keeps_browser_details_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: tuple[BrowserError | TimeoutError, str],
) -> None:
    failure, message = scenario
    context = MagicMock()
    context.__aenter__ = AsyncMock(side_effect=failure)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(login_module, "async_playwright", lambda: context)
    paths = Paths(tmp_path)

    with pytest.raises(MoodleError, match=message):
        anyio.run(login_module.login, paths)

    status = SessionStore(paths).status()
    assert status["state"] == "AUTH_REQUIRED"
    assert message in status["message"]
    assert "internal browser details" not in status["message"]
