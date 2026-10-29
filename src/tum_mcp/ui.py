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
from tum_mcp.connect import ServiceChoice, available_services
from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError

STYLES = {
    "title": "bold",
    "muted": "dim",
    "accent": "cyan",
    "ready": "green",
    "configured": "blue",
    "attention": "yellow",
    "failed": "red",
}


class State(StrEnum):
    READY = "Ready"
    UPDATED = "Updated"
    ENABLED = "Enabled"
    CONFIGURED = "Not verified"
    MISSING = "Not installed"
    UNCONFIGURED = "Not configured"
    ACTION = "Action needed"
    FAILED = "Failed"
    DISABLED = "Disabled"
    UNAVAILABLE = "Unavailable"
    INFO = "Info"


def terminal_console() -> Console:
    size = shutil.get_terminal_size(fallback=(80, 25))
    return Console(
        theme=Theme(STYLES),
        no_color="NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb",
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


def detail_rows(console: Console, rows: list[tuple[str, str]]) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(max_width=min(36, console.width // 2), overflow="fold")
    if console.width >= 70:
        table.add_column(overflow="fold")
    for label, detail in rows:
        if console.width < 70:
            table.add_row(Text(label, style="bold"))
            table.add_row(Text("  " + detail))
        else:
            table.add_row(Text(label), Text(detail))
    console.print(table)
    console.print()


def state_style(state: State) -> str:
    match state:
        case State.READY | State.UPDATED | State.ENABLED:
            return "ready"
        case State.CONFIGURED:
            return "configured"
        case State.ACTION:
            return "attention"
        case State.FAILED:
            return "failed"
        case State.MISSING | State.UNCONFIGURED | State.DISABLED | State.UNAVAILABLE | State.INFO:
            return "muted"
        case unreachable:
            assert_never(unreachable)


def status_badge(state: State) -> Text:
    return Text.assemble(("● ", state_style(state)), state.value)


def status_rows(console: Console, rows: list[tuple[str, State, str]]) -> None:
    narrow = console.width < 70
    table = Table.grid(padding=(0, 2), expand=False)
    table.add_column(no_wrap=not narrow)
    if not narrow:
        table.add_column(no_wrap=True)
        table.add_column(overflow="fold")
    for label, state, detail in rows:
        state_text = status_badge(state)
        if narrow:
            table.add_row(Text.assemble((label, "bold"), "  ", state_text))
            table.add_row(Text("  " + detail))
            table.add_row("")
        else:
            table.add_row(Text(label), state_text, Text(detail))
    console.print(table)
    console.print()


def selector_style() -> questionary.Style:
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return questionary.Style([])
    return questionary.Style(
        [
            ("pointer", "fg:ansicyan bold"),
            ("highlighted", "bold"),
            ("selected", "noreverse bold"),
            ("instruction", ""),
            *[
                (name, f"fg:ansi{color}")
                for name, color in STYLES.items()
                if name in {"ready", "configured", "attention", "failed"}
            ],
            ("muted", "fg:ansibrightblack"),
        ]
    )


def selection_label(label: str, state: State) -> list[tuple[str, str]]:
    return [("", f"{label}  "), (f"class:{state_style(state)}", "● "), ("", state.value)]


def select_many[T](
    title: str, choices: tuple[tuple[T, str, State, bool], ...], *, exclusive: T | None = None
) -> tuple[T, ...] | None:
    """Choose actions independently from the displayed current status."""

    def valid(values: list[T]) -> bool | str:
        if not values:
            return "Select at least one available item."
        if exclusive is not None and exclusive in values and len(values) > 1:
            return "Choose All on its own, or select individual extensions."
        return True

    console = terminal_console()
    if os.environ.get("TERM") == "dumb":
        section(console, title)
        for index, (_, label, state, _selectable) in enumerate(choices, 1):
            console.print(Text.assemble(f"{index}. {label}  ", status_badge(state)))
        console.print("Enter numbers separated by commas. Ctrl+C cancels.")
        available = {str(index) for index, row in enumerate(choices, 1) if row[3]}
        while True:
            numbers = [value.strip() for value in console.input("Selection: ").split(",")]
            if numbers and all(value in available for value in numbers):
                selected = list(dict.fromkeys(choices[int(value) - 1][0] for value in numbers))
                accepted = valid(selected)
                if accepted is True:
                    return tuple(selected)
                console.print(accepted, markup=False)
                continue
            console.print("Choose at least one available item by number.")
    console.print("Up/down: move · Space: select")
    console.print("Enter: continue · Ctrl+C: cancel")
    console.print()
    result = questionary.checkbox(
        title,
        choices=[
            questionary.Choice(selection_label(label, state), value=value, disabled=not selectable)
            for value, label, state, selectable in choices
        ],
        qmark="",
        pointer=">",
        style=selector_style(),
        instruction="",
        validate=valid,
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
    ).unsafe_ask()
    return (
        tuple(value for value, _, _, enabled in choices if enabled and value in result)
        if result
        else None
    )


def select_services() -> tuple[ServiceChoice, ...] | None:
    from tum_mcp.diagnostics import collect_services

    console = terminal_console()
    report = collect_services()
    descriptions = {
        ServiceChoice.MOODLE: "Materials and downloads",
        ServiceChoice.ARTEMIS: "Exercises and feedback",
        ServiceChoice.ZULIP: "Course discussions",
        ServiceChoice.TUMONLINE: "Studies and courses",
        ServiceChoice.TUM_LIVE: "Lecture recordings",
    }
    choices = []
    for service in available_services():
        states = [
            item.state for item in report.services if item.label.split(" ")[0] == service.label
        ]
        state = (
            State.CONFIGURED
            if states and all(s == State.CONFIGURED for s in states)
            else states[0]
            if states
            else State.UNCONFIGURED
        )
        label = (
            service.label if console.width < 70 else f"{service.label:<10} {descriptions[service]}"
        )
        choices.append((service, label, state, True))
    return select_many("Choose services", tuple(choices))


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
        style=selector_style(),
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
    ).unsafe_ask()
    match result:
        case BrowserChoice():
            return result
        case None:
            raise KeyboardInterrupt
        case _:
            raise BrowserSetupError("The browser selection could not be read. Run connect again.")
