"""Consumer QA must not fall back to the user's ordinary session directory."""

import browser_consumer_fixture
import pytest


def test_consumer_refuses_to_open_browsers_without_a_disposable_data_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TUM_MOODLE_DATA_DIR", raising=False)

    def discover() -> None:
        pytest.fail("Browser discovery ran before consumer data isolation was checked.")

    monkeypatch.setattr(browser_consumer_fixture, "discover_browsers", discover)
    with pytest.raises(AssertionError, match="requires TUM_MOODLE_DATA_DIR"):
        browser_consumer_fixture.main()
