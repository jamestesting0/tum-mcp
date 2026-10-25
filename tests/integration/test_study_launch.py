"""The short launcher serves the current project without changing agent commands."""

import subprocess
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx2
import pytest
from typer.testing import CliRunner

from tum_mcp import study_preview
from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code


def test_no_arguments_launches_current_project_at_a_stable_address(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a course project and an isolated preview boundary.
    monkeypatch.chdir(project)
    launches: list[tuple[Path, int, bool]] = []

    def preview(root: Path, port: int, *, open_browser: bool = False) -> None:
        launches.append((root, port, open_browser))

    monkeypatch.setattr(study_preview, "serve", preview)

    # When the user enters the short command without options.
    result = CliRunner().invoke(app, ["study"])

    # Then it launches this course automatically on the same origin each time.
    assert result.exit_code == 0, result.output
    assert launches == [(project.resolve(), 8765, True)]


@pytest.mark.parametrize("automatic", [True, False])
def test_launch_serves_current_project_on_a_free_port(
    project: Path, monkeypatch: pytest.MonkeyPatch, automatic: bool
) -> None:
    # Given a built course, with browser activation isolated from the real desktop.
    monkeypatch.chdir(project)
    monkeypatch.setattr(study_preview, "is_wsl", lambda: False)
    opened: list[str] = []
    served: list[str] = []

    def open_browser(url: str) -> int:
        opened.append(url)
        return 0

    def serve_once(server: ThreadingHTTPServer) -> None:
        server.timeout = 2
        worker = Thread(target=server.handle_request, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            with httpx2.Client(trust_env=False, timeout=2) as client:
                response = client.get(url)
                assert response.status_code == 200
                assert response.content == (project / "study/index.html").read_bytes()
                served.append(url)
        finally:
            worker.join(timeout=3)
        raise KeyboardInterrupt

    monkeypatch.setattr(study_preview.typer, "launch", open_browser)
    monkeypatch.setattr(ThreadingHTTPServer, "serve_forever", serve_once)

    # When launching directly, or using the existing unattended preview command.
    arguments = ["study", "--port", "0"] if automatic else ["study", "serve", ".", "--port", "0"]
    result = CliRunner().invoke(app, arguments)

    # Then the real HTTP server serves the selected course; only launch opens a tab.
    assert result.exit_code == 0, result.output
    assert len(served) == 1 and served[0] in result.output
    assert opened == (served if automatic else [])


def test_launcher_without_a_built_site_preserves_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an unrelated directory containing personal notes.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_bytes(b"Keep these notes")
    opened: list[str] = []
    monkeypatch.setattr(study_preview.typer, "launch", lambda url: opened.append(url))

    # When the short command is invoked outside a prepared course.
    result = CliRunner().invoke(app, ["study"])

    # Then it requests preparation and neither opens the browser nor creates files.
    assert isinstance(result.exception, CampusError)
    assert result.exception.code == Code.ACTION_REQUIRED
    assert opened == []
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        "notes.txt": b"Keep these notes"
    }


def test_help_does_not_launch_a_server_or_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the real CLI with server startup prohibited.
    def unexpected_launch(project: Path, port: int, *, open_browser: bool = False) -> None:
        pytest.fail("Help must not start a preview.")

    monkeypatch.setattr(study_preview, "serve", unexpected_launch)

    # When requesting command help.
    result = CliRunner().invoke(app, ["study", "--help"])

    # Then help completes without entering the launcher.
    assert result.exit_code == 0


def test_occupied_port_is_reported_without_opening_a_browser(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a port already bound by another process.
    monkeypatch.chdir(project)
    opened: list[str] = []
    monkeypatch.setattr(study_preview.typer, "launch", lambda url: opened.append(url))
    with ThreadingHTTPServer(("127.0.0.1", 0), study_preview.Handler) as occupied:
        # When the user requests that port for their course.
        result = CliRunner().invoke(app, ["study", "--port", str(occupied.server_port)])

    # Then the user gets an actionable error and no tab for an unrelated server.
    assert isinstance(result.exception, CampusError)
    assert result.exception.code == Code.ACTION_REQUIRED
    assert opened == []


@pytest.mark.parametrize("wsl", [False, True])
@pytest.mark.parametrize("browser_available", [False, True])
def test_browser_launch_failure_keeps_the_server_available(
    project: Path, monkeypatch: pytest.MonkeyPatch, wsl: bool, browser_available: bool
) -> None:
    # Given native or WSL browser activation, which may fail or time out.
    monkeypatch.chdir(project)
    monkeypatch.setattr(study_preview, "is_wsl", lambda: wsl)
    shell = "/Windows path/powershell.exe"
    monkeypatch.setattr(study_preview.shutil, "which", lambda name: shell)
    opened: list[str] = []
    served: list[str] = []

    def open_browser(url: str) -> int:
        opened.append(url)
        return 0 if browser_available else 1

    def windows_launch(
        args: list[str], *, capture_output: bool, timeout: int, check: bool
    ) -> subprocess.CompletedProcess[bytes]:
        assert len(args) == 5
        assert args[:4] == [shell, "-NoProfile", "-NonInteractive", "-Command"]
        assert capture_output and timeout == 10 and not check
        if not browser_available:
            raise subprocess.TimeoutExpired(args, timeout)
        opened.append(args[4].removeprefix("Start-Process '").removesuffix("'"))
        return subprocess.CompletedProcess(args, 0)

    def stop(server: ThreadingHTTPServer) -> None:
        served.append(f"http://127.0.0.1:{server.server_port}/")
        raise KeyboardInterrupt

    monkeypatch.setattr(study_preview.typer, "launch", open_browser)
    monkeypatch.setattr(study_preview.subprocess, "run", windows_launch)
    monkeypatch.setattr(ThreadingHTTPServer, "serve_forever", stop)

    # When starting the app with the short command.
    result = CliRunner().invoke(app, ["study", "--port", "0"])

    # Then browser failure cannot stop preview startup or hide the usable URL.
    assert result.exit_code == 0, result.output
    assert len(served) == 1 and served[0] in result.output
    assert opened == ([] if wsl and not browser_available else served)
