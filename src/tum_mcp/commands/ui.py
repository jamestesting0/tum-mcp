"""Shared, terminal-aware primitives. Design working notes stay in docs/local/."""

import os
import shutil
from enum import StrEnum
from typing import assert_never

import questionary
from prompt_toolkit.output import ColorDepth
from rich.console import Console, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from tum_mcp import __version__
from tum_mcp.commands.terminal_input import numbered_input, with_escape
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
    """Values are the stable --json vocabulary; `label` and `symbol` are what people read."""

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

    @property
    def label(self) -> str:
        match self:
            case State.ENABLED:
                return "On"
            case State.DISABLED:
                return "Off"
            case State.CONFIGURED:
                return "Not checked"
            case State.UNCONFIGURED:
                return "Not set up"
            case State.ACTION:
                return "Needs action"
            case State.INFO:
                return "Note"
            case _:
                return self.value

    @property
    def symbol(self) -> str:
        match self:
            case State.READY | State.UPDATED | State.ENABLED:
                return "✓"
            case State.ACTION:
                return "!"
            case State.FAILED:
                return "✗"
            case State.CONFIGURED | State.INFO:
                return "–"
            case State.MISSING | State.UNCONFIGURED | State.DISABLED | State.UNAVAILABLE:
                return "○"
            case unreachable:
                assert_never(unreachable)


def terminal_console() -> Console:
    size = shutil.get_terminal_size(fallback=(80, 25))
    return Console(
        theme=Theme(STYLES),
        no_color="NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb",
        highlight=False,
        width=min(size.columns, 100),
        height=size.lines,
    )


def heading(
    console: Console, title: str, description: str | None = None, *, version: bool = False
) -> None:
    console.print(
        Text.assemble(
            ("TUM MCP", "title"), f"  {title}", *(("  ", (__version__, "muted")) if version else ())
        )
    )
    if description:
        console.print(Text(description, style="muted"))
    console.print()


def section(console: Console, title: str) -> None:
    console.print(Text(title, style="title"))


def narrow(console: Console) -> bool:
    return console.width < 70


def print_block(console: Console, renderable: RenderableType) -> None:
    """Print without the cell padding Rich adds after the last column."""
    with console.capture() as captured:
        console.print(renderable)
    _ = console.file.write("\n".join(line.rstrip(" ") for line in captured.get().split("\n")))
    console.file.flush()


def stacked(console: Console, heading_text: Text, detail: str) -> None:
    console.print(heading_text)
    if detail:
        print_block(console, Padding(Text(detail), (0, 0, 0, 2)))


def detail_rows(console: Console, rows: list[tuple[str, str]]) -> None:
    if narrow(console):
        for label, detail in rows:
            stacked(console, Text(label, style="bold"), detail)
        console.print()
        return
    table = Table.grid(padding=(0, 2))
    table.add_column(max_width=min(36, console.width // 2), overflow="fold")
    table.add_column(overflow="fold")
    for label, detail in rows:
        table.add_row(Text(label), Text(detail))
    print_block(console, table)
    console.print()


def state_style(state: State) -> str:
    match state:
        case State.READY | State.UPDATED | State.ENABLED:
            return "ready"
        case State.ACTION:
            return "attention"
        case State.FAILED:
            return "failed"
        case (
            State.CONFIGURED
            | State.MISSING
            | State.UNCONFIGURED
            | State.DISABLED
            | State.UNAVAILABLE
            | State.INFO
        ):
            return "muted"
        case unreachable:
            assert_never(unreachable)


def status_badge(state: State) -> Text:
    return Text.assemble((state.symbol + " ", state_style(state)), state.label)


def status_rows(console: Console, rows: list[tuple[str, State, str]]) -> None:
    if narrow(console):
        for label, state, detail in rows:
            stacked(console, Text.assemble((label, "bold"), "  ", status_badge(state)), detail)
        console.print()
        return
    table = Table.grid(padding=(0, 2), expand=False)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(overflow="fold")
    for label, state, detail in rows:
        table.add_row(Text(label), status_badge(state), Text(detail))
    print_block(console, table)
    console.print()


def count(number: int, singular: str, plural: str | None = None) -> str:
    return f"{number} {singular if number == 1 else plural or singular + 's'}"


def next_steps(console: Console, steps: list[str], title: str = "Next") -> None:
    if not steps:
        return
    section(console, title)
    for index, step in enumerate(steps, 1):
        console.print(Text(f"{index}. {step}"))
    console.print()


def hint(console: Console, text: str) -> None:
    print_block(console, Text(text, style="muted"))


def fit(text: str, console: Console, used: int) -> str:
    """Shorten picker descriptions so each choice stays on one line."""
    import textwrap

    return textwrap.shorten(text, max(12, console.width - used - 8), placeholder="…")


CLIENT_LABELS = {
    "codex": "Codex",
    "claude": "Claude Code",
    "cursor": "Cursor",
    "antigravity": "Antigravity",
    "generic": "Other app (mcp.json)",
}


def client_label(name: str, host: str = "local") -> str:
    return CLIENT_LABELS.get(name, name.title()) + (" (Windows)" if host == "windows" else "")


MULTI_HINT = "↑/↓ move · Space select · Enter confirm · Esc cancel"
SINGLE_HINT = "↑/↓ move · Enter choose · Esc cancel"


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


def selection_label(label: str, state: State | str | None) -> list[tuple[str, str]]:
    match state:
        case None:
            return [("", label)]
        case State():
            return [("", label), ("class:muted", f"  {state.label}")]
        case str():
            return [("", label), ("class:muted", f"  {state}")]


def locked_reason(selectable: bool | str) -> str | None:
    """A row that cannot be picked says why; True means selectable."""
    if selectable is True:
        return None
    return selectable or "unavailable"


def select_many[T](
    title: str,
    choices: tuple[tuple[T, str, State | str | None, bool | str], ...],
    *,
    exclusive: T | None = None,
    defaults: tuple[T, ...] = (),
    optional: bool = False,
) -> tuple[T, ...] | None:
    """Choose actions independently from the displayed current status."""

    def valid(values: list[T]) -> bool | str:
        if not values and not optional:
            return "Select at least one available item."
        if exclusive is not None and exclusive in values and len(values) > 1:
            return "Choose Everything on its own, or select individual workflows."
        return True

    console = terminal_console()
    selected_defaults = tuple(
        value
        for value, _, _, selectable in choices
        if locked_reason(selectable) is None and value in defaults
    )
    if os.environ.get("TERM") == "dumb":
        section(console, title)
        for index, (_, label, state, selectable) in enumerate(choices, 1):
            reason = locked_reason(selectable)
            status = state.label if isinstance(state, State) else state
            suffix = f" ({reason})" if reason else f"  {status}" if status else ""
            console.print(Text(f"{index}. {label}{suffix}"))
        console.print("Enter numbers separated by commas · Esc cancels")
        default_numbers = ",".join(
            str(index) for index, row in enumerate(choices, 1) if row[0] in selected_defaults
        )
        available = {
            str(index) for index, row in enumerate(choices, 1) if locked_reason(row[3]) is None
        }
        while True:
            prompt = f"Selection [{default_numbers}]: " if default_numbers else "Selection: "
            answer = numbered_input(prompt).strip()
            if optional and not answer and not default_numbers:
                return ()
            numbers = [value.strip() for value in (answer or default_numbers).split(",")]
            if numbers and all(value in available for value in numbers):
                selected = list(dict.fromkeys(choices[int(value) - 1][0] for value in numbers))
                accepted = valid(selected)
                if accepted is True:
                    return tuple(selected)
                console.print(accepted, markup=False)
                continue
            console.print("Choose at least one available item by number.")
    hint(console, MULTI_HINT)
    width = (
        max(len(label) for _, label, state, _ in choices if state is not None)
        if any(state is not None for _, _, state, _ in choices)
        else 0
    )
    result = with_escape(
        questionary.checkbox(
            title,
            choices=[
                questionary.Choice(
                    label
                    if locked_reason(selectable)
                    else selection_label(label.ljust(width), state),
                    value=value,
                    disabled=locked_reason(selectable),
                    checked=value in selected_defaults,
                )
                for value, label, state, selectable in choices
            ],
            qmark="",
            pointer=">",
            style=selector_style(),
            instruction="",
            validate=valid,
            color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
        )
    ).unsafe_ask()
    return (
        tuple(
            value
            for value, _, _, selectable in choices
            if locked_reason(selectable) is None and value in result
        )
        if result is not None
        else None
    )


def select_services() -> tuple[ServiceChoice, ...] | None:
    from tum_mcp.diagnostics import collect_services

    console = terminal_console()
    report = collect_services(live="stale")
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
            State.ACTION if State.ACTION in states else states[0] if states else State.UNCONFIGURED
        )
        label = (
            service.label if console.width < 70 else f"{service.label:<10} {descriptions[service]}"
        )
        choices.append((service, label, state, True))
    return select_many(
        "Choose services to sign in to",
        tuple(choices),
        defaults=tuple(service for service, _, state, _ in choices if state == State.ACTION),
    )


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
        console.print("Choose browser")
        for index, browser in enumerate(browsers, 1):
            console.print(Text(f"{index}. {browser.label}"))
        console.print("Enter a browser number · Esc cancels")
        while True:
            answer = numbered_input("Browser number: ").strip()
            if answer.isdecimal() and 1 <= int(answer) <= len(browsers):
                return browsers[int(answer) - 1]
            console.print("Choose one of the listed browser numbers.")
    hint(console, SINGLE_HINT)
    result = with_escape(
        questionary.select(
            "Choose browser",
            choices=[questionary.Choice(browser.label, value=browser) for browser in browsers],
            qmark="",
            pointer=">",
            instruction=" ",
            style=selector_style(),
            color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
        )
    ).unsafe_ask()
    match result:
        case BrowserChoice():
            return result
        case None:
            raise KeyboardInterrupt
        case _:
            raise BrowserSetupError(
                "The browser selection could not be read. Run tum-mcp login again."
            )
