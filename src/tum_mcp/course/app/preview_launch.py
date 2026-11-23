import shutil
import subprocess
import webbrowser
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import typer

from tum_mcp.course.app.preview import Handler, PreviewServer
from tum_mcp.course.app.preview_ports import (
    OCCUPIED,
    PreviewPorts,
    PreviewSession,
    automatic_preview,
)
from tum_mcp.course.project.paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import is_wsl


def _open_browser(url: str) -> bool:
    try:
        if not is_wsl():
            return typer.launch(url) == 0
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if shell is None:
            return False
        result = subprocess.run(  # noqa: S603
            [shell, "-NoProfile", "-NonInteractive", "-Command", f"Start-Process '{url}'"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, webbrowser.Error):
        return False


def _show_publication(root: Path) -> None:
    from tum_mcp.course.app.publish_models import load_publication

    try:
        publication = load_publication(root)
    except CampusError:
        print(
            "Saved GitHub publication settings need review; local preview is available.",
            flush=True,
        )
        return
    if publication is None:
        return
    if publication.hosted_url:
        print(f"Hosted study: {publication.hosted_url}", flush=True)
    print(f"GitHub repository: https://github.com/{publication.repository}", flush=True)
    if publication.deployed_commit != publication.commit:
        print("Latest hosted update is pending verification.", flush=True)
    if not publication.auto_sync:
        print("Automatic publication is paused.", flush=True)


def _run_preview(root: Path, session: PreviewSession, *, open_browser: bool) -> None:
    url = f"http://127.0.0.1:{session.ports.active}/"
    print(f"Study preview: {url}", flush=True)
    if session.ports.active != session.ports.preferred:
        print(
            f"Port {session.ports.preferred} is unavailable. "
            + "Browser progress is stored separately at this temporary address.",
            flush=True,
        )
    if session.server is None:
        print("Reusing the preview already running for this project.", flush=True)
    _show_publication(root)
    try:
        if open_browser and not _open_browser(url):
            print("Open the URL above in your browser.", flush=True)
        if session.server is not None:
            session.server.serve_forever()
    except KeyboardInterrupt:
        if session.server is not None:
            print("Study preview stopped.")


def serve(project: Path, port: int | None, *, open_browser: bool = False) -> None:
    root = project.expanduser().resolve()
    site = app_path(root, "index.html").parent
    if not (site / "index.html").is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Build the study site first.")

    def bind(candidate: int) -> ThreadingHTTPServer:
        return PreviewServer(("127.0.0.1", candidate), partial(Handler, directory=str(site)))

    if port is None:
        with automatic_preview(root, bind) as session:
            _run_preview(root, session, open_browser=open_browser)
        return

    try:
        server = bind(port)
    except OSError as error:
        if error.errno not in OCCUPIED:
            raise
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Port {port} is in use. Reuse the preview if it serves this project, or run "
            + "tum-mcp study serve PROJECT --port PORT with a different port. "
            + "Use --port 0 for a free port. Keep the same port to retain browser progress.",
        ) from None
    with server:
        ports = PreviewPorts(preferred=server.server_port, active=server.server_port)
        _run_preview(root, PreviewSession(ports, server), open_browser=open_browser)
