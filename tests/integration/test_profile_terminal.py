import os
from pathlib import Path

import pytest
from test_cli_terminal import run_selector

from tum_mcp.browser_profiles import create_profile, remember_browser
from tum_mcp.moodle.browsers import BrowserChoice

pytestmark = pytest.mark.skipif(os.name == "nt", reason="PTY keyboard QA uses POSIX terminal APIs.")


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("terminal", ["xterm-256color", "dumb"])
def test_last_browser_or_profile_is_selected_by_enter(
    tmp_path: Path,
    terminal: str,
    saved: bool,
) -> None:
    browser = BrowserChoice("Second browser", "second")
    selected = create_profile(browser, "Study") if saved else browser
    remember_browser(selected)
    code, output = run_selector(
        tmp_path, b"1\n" if terminal == "dumb" else b" \r", browser_keys=b"\r", terminal=terminal
    )
    assert code == 0, output
    assert "BROWSER=second" in output
    assert "PROFILE=" + (selected.profile.id if saved else "temporary") in output
