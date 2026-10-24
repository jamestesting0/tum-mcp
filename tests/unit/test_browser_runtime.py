import hashlib
import io
import os
import sys
import zipfile
from pathlib import Path

import httpx2
import pytest
from playwright.sync_api import sync_playwright

from tum_moodle import browser_runtime
from tum_moodle.browsers import BrowserChoice, BrowserSetupError


@pytest.mark.parametrize("tampered", [False, True])
def test_windows_runtime_download_verifies_archive_and_executable_hashes(
    monkeypatch: pytest.MonkeyPatch, tampered: bool
) -> None:
    data = b"synthetic-executable-never-run"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"node-v{browser_runtime.NODE_VERSION}-win-x64/node.exe", data)
    payload = buffer.getvalue()
    monkeypatch.setattr(
        browser_runtime,
        "NODE_HASHES",
        {
            "x64": (
                hashlib.sha256(payload).hexdigest(),
                hashlib.sha256(data).hexdigest(),
            )
        },
    )

    def request(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "nodejs.org" and request.method == "GET"
        return httpx2.Response(200, content=payload + b"tampered" if tampered else payload)

    monkeypatch.setattr(
        browser_runtime.httpx2, "HTTPTransport", lambda **kwargs: httpx2.MockTransport(request)
    )
    if tampered:
        with pytest.raises(BrowserSetupError, match="checksum failed"):
            browser_runtime._download_node("x64")
    else:
        assert browser_runtime._download_node("x64") == data


@pytest.mark.skipif(sys.platform == "win32", reason="WSL shim requires a POSIX host.")
def test_wsl_driver_shim_carries_real_playwright_protocol_and_restores_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import playwright

    node = Path(playwright.__file__).parent / "driver/node"
    monkeypatch.setattr(browser_runtime, "windows_node", lambda: node)
    monkeypatch.setattr(browser_runtime, "wsl_path", lambda path, **kwargs: path)
    monkeypatch.setenv("DEBUGP", "synthetic-do-not-log-protocol")
    previous = os.environ.get("PLAYWRIGHT_NODEJS_PATH")
    with browser_runtime.browser_driver(BrowserChoice("Test", "unused", True)):
        shim = Path(os.environ["PLAYWRIGHT_NODEJS_PATH"])
        assert shim.is_file() and "DEBUGP" not in os.environ
        with sync_playwright() as driver:
            assert driver.chromium.name == "chromium"
    assert not shim.exists()
    assert os.environ.get("PLAYWRIGHT_NODEJS_PATH") == previous
    assert os.environ["DEBUGP"] == "synthetic-do-not-log-protocol"
