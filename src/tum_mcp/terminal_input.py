"""Escape cancellation for checkbox, choice and plain numbered prompts."""

import sys

import questionary
from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent, merge_key_bindings
from prompt_toolkit.output import DummyOutput


def escape_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("escape")
    def cancel(event: KeyPressEvent) -> None:
        event.app.exit(exception=KeyboardInterrupt)

    return bindings


def with_escape(question: questionary.Question) -> questionary.Question:
    application = question.application
    # Both escape-sequence decoding and ambiguous bindings otherwise delay cancellation.
    application.ttimeoutlen = application.timeoutlen = 0.05
    application.key_bindings = merge_key_bindings(
        [
            binding
            for binding in (application.key_bindings, escape_bindings())
            if binding is not None
        ]
    )
    return question


def numbered_input(message: str) -> str:
    """Keep single-line editing and Escape without ANSI output in basic terminals."""
    session: PromptSession[str] = PromptSession(
        key_bindings=escape_bindings(), output=DummyOutput()
    )
    session.app.ttimeoutlen = session.app.timeoutlen = 0.05
    previous = 0
    ready = False

    def redraw(buffer: Buffer) -> None:
        nonlocal previous
        if not ready:
            return
        text = buffer.text
        sys.stdout.write(
            "\r"
            + message
            + text
            + " " * max(0, previous - len(text))
            + "\r"
            + message
            + text
            + "\b" * (len(text) - buffer.cursor_position)
        )
        sys.stdout.flush()
        previous = len(text)

    session.default_buffer.on_text_changed += redraw
    session.default_buffer.on_cursor_position_changed += redraw

    def start(_application: Application[str]) -> None:
        nonlocal ready
        if not ready:
            ready = True
            redraw(session.default_buffer)

    session.app.before_render += start
    try:
        return session.prompt()
    finally:
        sys.stdout.write("\n")
        sys.stdout.flush()
