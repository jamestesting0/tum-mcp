"""Metadata discovery commands for connected campus accounts."""

from typing import Annotated, assert_never

import typer

from tum_mcp.extensions import require_lecture
from tum_mcp.settings import Provider, find_account


def discover(
    provider: Annotated[
        Provider, typer.Argument(metavar="SERVICE", help="artemis, zulip or tum_live.")
    ],
    account_id: Annotated[
        str,
        typer.Argument(metavar="ACCOUNT", help="Its account_id in tum-mcp status --json."),
    ],
    include_past: Annotated[
        bool, typer.Option(help="Include past Artemis courses as well as active courses.")
    ] = False,
) -> None:
    """List the courses or channels an account can read (JSON)."""
    if include_past and provider != Provider.ARTEMIS:
        raise typer.BadParameter("--include-past applies to Artemis course discovery only.")
    if provider == Provider.TUM_LIVE:
        require_lecture()
    from tum_mcp.transport import API

    api = API(find_account(account_id, provider))
    match provider:
        case Provider.ZULIP:
            from tum_mcp.zulip import Zulip

            typer.echo(Zulip(api).channels().model_dump_json(indent=2))
        case Provider.ARTEMIS:
            from tum_mcp.artemis import Artemis

            typer.echo(Artemis(api).courses(include_past=include_past).model_dump_json(indent=2))
        case Provider.TUM_LIVE:
            from tum_mcp.tum_live import TumLive

            typer.echo(TumLive(api).courses().model_dump_json(indent=2))
        case unreachable:
            assert_never(unreachable)
