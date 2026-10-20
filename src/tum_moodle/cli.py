import logging

import anyio
import typer

from tum_moodle.auth import SessionStore
from tum_moodle.config import Paths
from tum_moodle.login import login

app = typer.Typer(no_args_is_help=True)


@app.command("login")
def login_command() -> None:
    """Open a private browser window for personal TUM sign-in."""
    typer.echo("Complete TUM sign-in in the opened browser. Do not send credentials in chat.")
    anyio.run(login, Paths.default())
    typer.echo("Moodle session encrypted using your system's native credential store.")


@app.command()
def status() -> None:
    """Report saved-session status without exposing account data."""
    typer.echo(SessionStore(Paths.default()).status())


@app.command()
def serve() -> None:
    """Start the MCP stdio server."""
    from tum_moodle.server import server

    logging.getLogger("httpx2").setLevel(logging.WARNING)
    server.run()
