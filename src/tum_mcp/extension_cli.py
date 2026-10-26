"""Explicit commands for optional integrations."""

import json
from typing import Literal

import typer

from tum_mcp.extensions import selection, set_studocu

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def install(name: Literal["studocu"]) -> None:
    """Install an optional extension into managed clients."""
    typer.echo(json.dumps({"extension": name, "state": set_studocu(True)}))


@app.command()
def status() -> None:
    """Show the local extension selection without contacting a provider."""
    typer.echo(selection().model_dump_json(indent=2))


@app.command()
def remove(name: Literal["studocu"]) -> None:
    """Disable an extension and remove unchanged managed skills."""
    typer.echo(json.dumps({"extension": name, "state": set_studocu(False)}))
