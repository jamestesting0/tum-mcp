"""Explicit local Git credential import and isolated testing."""

import getpass
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

import typer
from pydantic import SecretStr

from tum_mcp.artemis import Artemis
from tum_mcp.credentials import RepositorySecret, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.git_ops import repository_url
from tum_mcp.runner import run_tests
from tum_mcp.settings import Provider, find_account
from tum_mcp.transport import API

app = typer.Typer(no_args_is_help=True)


@app.command("connect-git")
def connect_git(
    account_id: str,
    course_id: int,
    exercise_id: int,
    mode: Literal["graded", "practice"] = "graded",
) -> None:
    """Import an existing participation token through hidden local input; never provisions one."""
    if not sys.stdin.isatty():
        raise CampusError(
            Code.ACTION_REQUIRED, "Import Git credentials from your own interactive terminal."
        )
    account = find_account(account_id, Provider.ARTEMIS)
    provider = Artemis(API(account))
    view = provider.exercise(course_id, exercise_id)
    participation = provider.participation(view.exercise, mode)
    if not participation.repository_uri:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "No participation repository is exposed.")
    expected = repository_url(participation.repository_uri.get_secret_value(), account)
    typer.echo(f"Import an existing token for {expected}. This command does not create tokens.")
    value = getpass.getpass("Paste the clone URL here (hidden): ")
    parsed = urlsplit(value)
    if repository_url(value, account) != expected or not parsed.username or not parsed.password:
        raise CampusError(
            Code.SCOPE_DENIED, "Clone URL does not match this exact participation or lacks a token."
        )
    secret = RepositorySecret(
        url=expected,
        username=SecretStr(unquote(parsed.username)),
        password=SecretStr(unquote(parsed.password)),
    )
    vault = Vault()
    current = vault.load(account)
    repositories = tuple(item for item in current.repositories if item.url != expected) + (secret,)
    vault.save(account, current.model_copy(update={"repositories": repositories}))
    typer.echo("Repository credential encrypted. No clone or push was performed.")


@app.command("test")
def test_workspace(workspace: Path, recipe: str) -> None:
    """Run one locally approved test recipe in an isolated container."""
    typer.echo(run_tests(workspace, recipe).model_dump_json(indent=2))
