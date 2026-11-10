import os

import questionary
from prompt_toolkit.output import ColorDepth
from rich.text import Text

from tum_mcp.commands.terminal_input import numbered_input, with_escape
from tum_mcp.commands.ui import SINGLE_HINT, hint, selector_style, terminal_console


def choose[T](title: str, choices: tuple[tuple[T, str], ...]) -> T:
    if not choices:
        raise KeyboardInterrupt
    console = terminal_console()
    if os.environ.get("TERM") == "dumb":
        console.print(Text(title))
        for index, (_, label) in enumerate(choices, 1):
            console.print(Text(f"{index}. {label}"))
        console.print("Enter a number (default 1) · Esc cancels")
        while True:
            answer = numbered_input("Selection [1]: ").strip() or "1"
            if answer.isdecimal() and 1 <= int(answer) <= len(choices):
                return choices[int(answer) - 1][0]
            console.print("Choose one of the listed numbers.")
    hint(console, SINGLE_HINT)
    result = with_escape(
        questionary.select(
            title,
            choices=[
                questionary.Choice(label, value=index) for index, (_, label) in enumerate(choices)
            ],
            default=0,
            qmark="",
            pointer=">",
            instruction=" ",
            style=selector_style(),
            color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
        )
    ).unsafe_ask()
    if result is None:
        raise KeyboardInterrupt
    return choices[result][0]
