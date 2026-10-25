import hashlib
import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx2
import pytest
from playwright.sync_api import sync_playwright

from tum_mcp.moodle import browser_runtime
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError


@pytest.mark.parametrize("mode", ["success", "text-corruption", "failure", "timeout"])
def test_pipe_probe_uses_binary_round_trip_not_wsl_version(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert command[:2] == ["node.exe", "--eval"]
        assert kwargs["input"] == b"tum-browser-pipe\x00\xff\n"
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 10)
        return subprocess.CompletedProcess(
            command,
            1 if mode == "failure" else 0,
            kwargs["input"] if mode != "text-corruption" else b"corrupted",
        )

    monkeypatch.setattr(browser_runtime.subprocess, "run", run)
    assert browser_runtime._direct_pipes_work(Path("node.exe")) == (mode == "success")


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


@pytest.mark.skipif(sys.platform != "win32", reason="Exercises the real Windows native pipe relay.")
def test_native_windows_relay_flushes_messages_before_stdin_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import queue
    import shlex
    import threading

    import playwright
    import psutil

    node = Path(playwright.__file__).parent / "driver/node.exe"
    monkeypatch.setattr(browser_runtime, "wsl_path", lambda path, **kwargs: path)
    command = shlex.split(
        browser_runtime._native_pipe_relay(node, "unused", "process.stdin.pipe(process.stdout);")
    )[1:]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)  # noqa: S603
    result: queue.Queue[bytes] = queue.Queue()
    payload = b"incremental-synthetic-frame\x00\xff\n"
    try:
        assert process.stdin is not None and process.stdout is not None
        # Keep stdin open: a missing per-frame flush deadlocks interactive Playwright.
        process.stdin.write(payload)
        process.stdin.flush()
        threading.Thread(
            target=lambda: result.put(process.stdout.read(len(payload))), daemon=True
        ).start()
        assert result.get(timeout=30) == payload
        process.stdin.close()
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            parent = psutil.Process(process.pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            process.kill()
            process.wait(timeout=10)
