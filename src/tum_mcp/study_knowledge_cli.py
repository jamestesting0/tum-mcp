"""Register local knowledge commands on the existing study CLI."""

from pathlib import Path
from typing import Annotated

import typer

from tum_mcp.study_knowledge_models import Purpose
from tum_mcp.study_knowledge_packet import encoded
from tum_mcp.study_knowledge_query import context as get_context
from tum_mcp.study_knowledge_query import impact as get_impact


def register(app: typer.Typer) -> None:
    @app.command()
    def context(
        project: Path,
        query: Annotated[str | None, typer.Argument()] = None,
        item: Annotated[str | None, typer.Option(help="Exact typed item reference.")] = None,
        concept: Annotated[str | None, typer.Option(help="Exact registry concept key.")] = None,
        purpose: Annotated[Purpose, typer.Option()] = "study",
        limit: Annotated[int, typer.Option(min=1, max=30)] = 12,
        max_bytes: Annotated[int, typer.Option(min=2048, max=65536)] = 24000,
    ) -> None:
        """Read bounded source-backed relationships; never extracts, builds or writes."""
        typer.echo(
            encoded(
                get_context(
                    project,
                    query,
                    item=item,
                    concept=concept,
                    purpose=purpose,
                    limit=limit,
                    max_bytes=max_bytes,
                )
            ).decode(),
            nl=False,
        )

    @app.command()
    def impact(
        project: Path,
        source: Annotated[str, typer.Option(help="Changed source key.")],
        limit: Annotated[int, typer.Option(min=1, max=30)] = 12,
        max_bytes: Annotated[int, typer.Option(min=2048, max=65536)] = 24000,
    ) -> None:
        """Read direct dependents and possible review targets for one source."""
        typer.echo(
            encoded(get_impact(project, source, limit=limit, max_bytes=max_bytes)).decode(),
            nl=False,
        )
