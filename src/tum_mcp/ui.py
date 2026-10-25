"""Shared, terminal-aware primitives. Design working notes stay in docs/local/."""

import os
import shutil
from enum import StrEnum
from typing import assert_never

import questionary
from prompt_toolkit.output import ColorDepth
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from tum_mcp import __version__
from tum_mcp.connect import ServiceChoice
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError

STYLES = {
    "title": "bold",
    "muted": "dim",
    "accent": "cyan",
    "ready": "green",
    "attention": "yellow",
    "failed": "red",
}


class State(StrEnum):
    READY = "Ready"
    UPDATED = "Updated"
    CONFIGURED = "Not verified"
    MISSING = "Not installed"
    UNCONFIGURED = "Not configured"
    ACTION = "Action needed"
    FAILED = "Failed"
    DISABLED = "Disabled"
    INFO = "Info"


def terminal_console() -> Console:
    size = shutil.get_terminal_size(fallback=(80, 25))
    return Console(
        theme=Theme(STYLES),
        no_color="NO_COLOR" in os.environ,
        highlight=False,
        width=min(size.columns, 100),
        height=size.lines,
    )


def heading(console: Console, command: str, description: str) -> None:
    console.print(Text.assemble(("TUM MCP", "title"), f"  {command}  ", (__version__, "muted")))
    console.print(Text(description, style="muted"))
    console.print()


def section(console: Console, title: str) -> None:
    console.print(Text(title, style="title"))


def status_rows(console: Console, rows: list[tuple[str, State, str]]) -> None:
    narrow = console.width < 70
    table = Table.grid(padding=(0, 2), expand=False)
    table.add_column(no_wrap=not narrow)
    if not narrow:
        table.add_column(no_wrap=True)
        table.add_column(overflow="fold")
    for label, state, detail in rows:
        match state:
            case State.READY | State.UPDATED:
                style = "ready"
            case State.FAILED:
                style = "failed"
            case State.ACTION | State.MISSING | State.UNCONFIGURED:
                style = "attention"
            case State.CONFIGURED | State.DISABLED | State.INFO:
                style = ""
            case unreachable:
                assert_never(unreachable)
        # Terminal ANSI palettes vary; keep the actual status in the default foreground.
        state_text = Text.assemble(("· " if style else "  ", style), state.value)
        if narrow:
            table.add_row(Text.assemble((label, "bold"), "  ", state_text))
            table.add_row(Text(detail))
            table.add_row("")
        else:
            table.add_row(Text(label), state_text, Text(detail))
    console.print(table)
    console.print()


def select_services() -> tuple[ServiceChoice, ...] | None:
    console = terminal_console()
    if os.environ.get("TERM") == "dumb":
        console.print("Connect services\n1. Moodle\n2. Artemis\n3. Zulip")
        console.print("Enter numbers separated by commas. Ctrl+C cancels.")
        choices = tuple(ServiceChoice)
        while True:
            answer = console.input("Services: ").strip()
            numbers = [value.strip() for value in answer.split(",")]
            if numbers and all(value in {"1", "2", "3"} for value in numbers):
                return tuple(dict.fromkeys(choices[int(value) - 1] for value in numbers))
            console.print("Choose at least one of 1, 2 or 3.")
    console.print("Up/down: move · Space: select")
    console.print("Enter: continue · Ctrl+C: cancel")
    console.print()
    labels = (
        ("Moodle · Materials", "Artemis · Exercises", "Zulip · Discussions")
        if console.width < 70
        else (
            "Moodle    Materials, forums and downloads",
            "Artemis   Programming exercises and feedback",
            "Zulip     Selected course discussions",
        )
    )
    colors = (
        []
        if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb"
        else [
            ("pointer", "fg:ansicyan bold"),
            ("highlighted", "bold"),
            ("selected", "noreverse bold"),
            ("instruction", ""),
        ]
    )
    result = questionary.checkbox(
        "Connect services",
        choices=[
            questionary.Choice(label, value=service.value)
            for label, service in zip(labels, ServiceChoice, strict=True)
        ],
        qmark="",
        pointer=">",
        style=questionary.Style(colors),
        instruction="",
        validate=lambda selected: True if selected else "Select at least one service.",
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
    ).unsafe_ask()
    return tuple(ServiceChoice(value) for value in result) if result else None


def select_browser(browsers: tuple[BrowserChoice, ...]) -> BrowserChoice:
    if not browsers:
        raise BrowserSetupError(
            "No supported Chromium browser found. Install Edge, Chrome, Brave, Chromium, "
            "Vivaldi or Opera, or set TUM_MCP_BROWSER to a compatible executable."
        )
    if len(browsers) == 1:
        return browsers[0]
    console = terminal_console()
    if os.environ.get("TERM") == "dumb":
        console.print("Browser")
        for index, browser in enumerate(browsers, 1):
            console.print(Text(f"{index}. {browser.label}"))
        while True:
            answer = console.input("Browser number: ").strip()
            if answer.isdecimal() and 1 <= int(answer) <= len(browsers):
                return browsers[int(answer) - 1]
            console.print("Choose one of the listed browser numbers.")
    console.print("Up/down: move · Enter: continue")
    console.print("Ctrl+C: cancel")
    result = questionary.select(
        "Browser",
        choices=[questionary.Choice(browser.label, value=browser) for browser in browsers],
        qmark="",
        pointer=">",
        instruction="",
        style=questionary.Style([("highlighted", "bold"), ("pointer", "bold")]),
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
    ).unsafe_ask()
    match result:
        case BrowserChoice():
            return result
        case None:
            raise KeyboardInterrupt
        case _:
            raise BrowserSetupError("The browser selection could not be read. Run connect again.")
