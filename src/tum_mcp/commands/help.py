"""One compact help layout for the campus CLI and all nested commands."""

import re

import click
import typer
from rich.text import Text
from typer.core import TyperArgument, TyperCommand, TyperGroup, TyperOption

from tum_mcp import __version__
from tum_mcp.commands.ui import detail_rows, section, terminal_console

ROOT_DESCRIPTION = "Campus tools and local study workflows."
ROOT_GROUPS = (
    ("Get started", ("setup", "login")),
    (
        "Manage",
        ("doctor", "install", "uninstall", "manage", "update", "logout", "skills", "version"),
    ),
    (
        "Used by your coding agent",
        ("study", "review", "lecture", "video-notes", "audio-notes", "discover", "serve"),
    ),
)
# Options the npm launcher handles before the Python backend runs.
LAUNCHER_OPTIONS = {
    "update": (("--local", "Refresh this version without checking npm for a newer release."),),
}
PANEL_ORDER = ("Setup", "Study", "Sources", "Author", "Check", "Publish", "Commands", "Advanced")
_DEFAULT = re.compile(r"\s*\[default: [^\]]*\]")


def option_record(parameter: TyperOption, context: click.Context) -> tuple[str, str] | None:
    record = parameter.get_help_record(context)
    if record is None:
        return None
    names, text = record
    if parameter.is_flag:
        text = _DEFAULT.sub("", text)
        if parameter.secondary_opts and parameter.default is False:
            names = names.split(" / ")[0]
    return names, text.strip()


def usage_line(command: TyperCommand | TyperGroup, context: click.Context) -> str:
    pieces = " ".join((context.command_path, *command.collect_usage_pieces(context)))
    return re.sub(r"\{([A-Z_]+)\}", r"\1", pieces)


def help_rows(
    command: TyperCommand | TyperGroup, context: click.Context
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    arguments: list[tuple[str, str]] = []
    options: list[tuple[str, str]] = []
    for parameter in command.get_params(context):
        match parameter:
            case TyperArgument():
                if record := parameter.get_help_record(context):
                    text = _DEFAULT.sub("", record[1]).replace("[required]", "").strip()
                    arguments.append((record[0], text))
            case TyperOption():
                if "--help" in parameter.opts:
                    continue
                if record := option_record(parameter, context):
                    options.append(record)
    if context.parent is not None and context.parent.parent is None:
        options.extend(LAUNCHER_OPTIONS.get(context.info_name or "", ()))
    if context.parent is None:
        options.append(("-h, --help", "Show this help."))
    return arguments, options


def command_groups(
    command: TyperGroup, context: click.Context
) -> list[tuple[str, list[tuple[str, str]]]]:
    names = command.list_commands(context)
    visible = {
        name: child
        for name in names
        if (child := command.get_command(context, name)) is not None and not child.hidden
    }
    if context.parent is None:
        grouped = [
            (title, [(name, visible[name].get_short_help_str(limit=120)) for name in members])
            for title, members in ROOT_GROUPS
        ]
        listed = {name for _, members in ROOT_GROUPS for name in members}
        if rest := [name for name in visible if name not in listed]:
            grouped.append(
                ("Other", [(name, visible[name].get_short_help_str(120)) for name in rest])
            )
        return grouped
    panels: dict[str, list[tuple[str, str]]] = {}
    for name, child in visible.items():
        panel = getattr(child, "rich_help_panel", None) or "Commands"
        panels.setdefault(panel, []).append((name, child.get_short_help_str(limit=120)))
    return sorted(
        panels.items(),
        key=lambda item: PANEL_ORDER.index(item[0]) if item[0] in PANEL_ORDER else 0,
    )


def command_help(command: TyperCommand | TyperGroup, context: click.Context) -> None:
    console = terminal_console()
    root = context.parent is None
    console.print(
        Text.assemble(
            ("TUM MCP", "title"),
            "  ",
            (__version__, "muted") if root else context.command_path,
        )
    )
    description = command.help or ROOT_DESCRIPTION
    console.print(Text(description.split("\n\n")[0], style="muted"))
    console.print()
    usage = usage_line(command, context)
    detail_rows(console, [("Usage", usage)])
    arguments, options = help_rows(command, context)
    for title, rows in (("Arguments", arguments), ("Options", options)):
        if rows:
            section(console, title)
            detail_rows(console, rows)
    if isinstance(command, TyperGroup):
        for title, rows in command_groups(command, context):
            section(console, title)
            detail_rows(console, rows)
    if command.epilog:
        console.print(command.epilog, markup=False)


def launcher_help(app: typer.Typer) -> dict[str, object]:
    """The help the npm launcher prints before the Python runtime exists."""
    group = typer.main.get_command(app)
    if not isinstance(group, TyperGroup):
        raise TypeError("The CLI root must be a command group.")
    commands: dict[str, dict[str, object]] = {}
    with group.context_class(group, info_name="tum-mcp") as context:
        groups = {
            title: [list(row) for row in rows] for title, rows in command_groups(group, context)
        }
        for name in ("setup", "install", "update", "uninstall"):
            child = group.get_command(context, name)
            if not isinstance(child, TyperCommand):
                raise TypeError(f"Launcher help needs the {name} command.")
            with child.context_class(child, info_name=name, parent=context) as sub:
                arguments, options = help_rows(child, sub)
                commands[name] = {
                    "description": child.help,
                    "usage": usage_line(child, sub),
                    "arguments": [list(row) for row in arguments],
                    "options": [list(row) for row in options],
                }
        _, root_options = help_rows(group, context)
        return {
            "description": ROOT_DESCRIPTION,
            "usage": usage_line(group, context),
            "options": [list(row) for row in root_options],
            "groups": groups,
            "commands": commands,
        }


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
    # Plain usage errors ("Error: ...") match the CLI's own error lines instead of a boxed panel.
    app.rich_markup_mode = None
    for command in app.registered_commands:
        command.cls = TerminalCommand
    for group in app.registered_groups:
        if group.typer_instance is not None:
            configure_help(group.typer_instance)
