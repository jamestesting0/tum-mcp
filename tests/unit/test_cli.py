import logging

import pytest

from tum_mcp.moodle import cli, server


def test_server_keeps_session_keys_out_of_request_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    request_logger = logging.getLogger("httpx2")
    monkeypatch.setattr(request_logger, "level", logging.NOTSET)

    def run() -> None:
        request_logger.info("POST https://www.moodle.tum.de/lib/ajax/service.php?sesskey=test-key")
        request_logger.warning("Network connection needs attention")

    monkeypatch.setattr(server.server, "run", run)
    with caplog.at_level(logging.INFO):
        cli.serve()

    assert "test-key" not in caplog.text
    assert "Network connection needs attention" in caplog.text
