"""One compact help layout for the campus CLI and all nested commands."""

import click
import typer
from typer.core import TyperArgument, TyperCommand, TyperGroup, TyperOption

from tum_mcp.ui import detail_rows, heading, section, terminal_console


def command_help(command: TyperCommand | TyperGroup, context: click.Context) -> None:
    console = terminal_console()
    heading(console, "Help", command.help or "Campus tools and local study workflows.")
    usage = " ".join((context.command_path, *command.collect_usage_pieces(context)))
    detail_rows(console, [("Usage", usage)])
    arguments: list[tuple[str, str]] = []
    options: list[tuple[str, str]] = []
    for parameter in command.get_params(context):
        match parameter:
            case TyperArgument():
                if record := parameter.get_help_record(context):
                    arguments.append(record)
            case TyperOption():
                if record := parameter.get_help_record(context):
                    options.append(record)
    if context.parent is not None and context.parent.parent is None:
        if context.info_name == "update":
            options.append(("--local", "Refresh the installed version without contacting npm."))
    for title, rows in (("Arguments", arguments), ("Options", options)):
        if rows:
            section(console, title)
            detail_rows(console, rows)
    if isinstance(command, TyperGroup):
        commands = []
        names = command.list_commands(context)
        if context.parent is None:
            order = (
                "setup",
                "login",
                "doctor",
                "install",
                "uninstall",
                "manage",
                "skills",
                "study",
                "lecture",
                "video-notes",
                "discover",
                "update",
                "logout",
                "serve",
                "version",
            )
            names = [name for name in order if name in names] + [
                name for name in names if name not in order
            ]
        for name in names:
            child = command.get_command(context, name)
            if child is not None and not child.hidden:
                commands.append((name, child.get_short_help_str(limit=120)))
        if commands:
            section(console, "Commands")
            detail_rows(console, commands)
    if command.epilog:
        console.print(command.epilog, markup=False)


class TerminalCommand(TyperCommand):
    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        command_help(self, ctx)


class TerminalGroup(TyperGroup):
    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        command_help(self, ctx)


def configure_help(app: typer.Typer) -> None:
    """Keep Typer's parsing; apply presentation after all commands are registered."""
    app.info.cls = TerminalGroup
    app.info.context_settings = {"help_option_names": ["-h", "--help"]}
    for command in app.registered_commands:
        command.cls = TerminalCommand
    for group in app.registered_groups:
        if group.typer_instance is not None:
            configure_help(group.typer_instance)
