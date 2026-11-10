"""Shared extension selection for install, uninstall and doctor."""

import json
import sys
from enum import StrEnum
from typing import assert_never

import typer

from tum_mcp.commands.ui import State, fit, heading, select_many, status_rows, terminal_console
from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import (
    lecture_installation,
    selection,
    set_audio_notes,
    set_course_memory,
    set_video_notes,
    uninstall_lecture,
)


class ExtensionName(StrEnum):
    LECTURE = "lecture"
    AUDIO_NOTES = "audio-notes"
    VIDEO_NOTES = "video-notes"
    COURSE_MEMORY = "course-memory"


EXTENSIONS = tuple(ExtensionName)
LABELS = {
    "lecture": "Lecture",
    "audio-notes": "Audio Notes",
    "video-notes": "Video Notes",
    "course-memory": "Course Memory",
}


def extension_rows() -> list[tuple[ExtensionName, str, State, str, str]]:
    """Name, label, state, what the workflow does, and its current status."""
    descriptions = {
        "lecture": "Notes and highlights from lecture recordings.",
        "audio-notes": "Create spoken lessons from prepared Study content.",
        "video-notes": "Create narrated, animated explainers from prepared Study content.",
        "course-memory": "Connect course workspaces with optional, source-checked local memory.",
    }
    rows = []
    for name in EXTENSIONS:
        try:
            match name:
                case ExtensionName.LECTURE:
                    installation = lecture_installation(strict=True)
                    enabled = installation is not None and installation.enabled
                case ExtensionName.AUDIO_NOTES:
                    enabled = selection().audio_notes
                case ExtensionName.VIDEO_NOTES:
                    enabled = selection().video_notes
                case ExtensionName.COURSE_MEMORY:
                    enabled = selection().course_memory
                case unreachable:
                    assert_never(unreachable)
            status = "" if enabled else f"Add with tum-mcp install {name}."
            if name == ExtensionName.VIDEO_NOTES and enabled:
                from tum_mcp.course.media.video_runtime import summary

                status = summary()
            state = State.ENABLED if enabled else State.DISABLED
            rows.append((name, LABELS[name], state, descriptions[name], status))
        except CampusError as error:
            rows.append((name, LABELS[name], State.FAILED, descriptions[name], error.message))
    return rows


def interactive_terminal() -> bool:
    return sys.stdin.isatty()


def remove_extensions(
    names: tuple[ExtensionName, ...], *, json_output: bool = False, show_heading: bool = True
) -> None:
    console = terminal_console()
    if not json_output and show_heading:
        heading(console, "Uninstall")
    reports = []
    rows: list[tuple[str, State, str]] = []
    needs_review = False
    for name in dict.fromkeys(names):
        match name:
            case ExtensionName.LECTURE:
                report = uninstall_lecture()
                review = bool(report["clients"]["needs_review"])
            case ExtensionName.AUDIO_NOTES:
                state = set_audio_notes(False) if selection().audio_notes else "disabled"
                report = {"extension": name, "state": state}
                review = state == "disabled_needs_review"
            case ExtensionName.VIDEO_NOTES:
                state = set_video_notes(False) if selection().video_notes else "disabled"
                report = {"extension": name, "state": state}
                review = state == "disabled_needs_review"
            case ExtensionName.COURSE_MEMORY:
                state = set_course_memory(False)
                report = {"extension": name, "state": state}
                review = state == "disabled_needs_review"
            case unreachable:
                assert_never(unreachable)
        needs_review |= review
        reports.append(report)
        rows.append(
            (
                LABELS[name],
                State.ACTION if review else State.DISABLED,
                "Removed; customized coding-app files need review." if review else "Removed.",
            )
        )
    if json_output:
        typer.echo(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2))
    else:
        status_rows(console, rows)
        console.print(
            "Your notes and saved data were kept. Restart your coding apps to apply this."
        )
    if needs_review:
        raise typer.Exit(2)


def confirm_full_removal(*, purge: bool, forget: bool) -> bool:
    from tum_mcp.commands.choices import choose

    console = terminal_console()
    console.print()
    removed = ["TUM MCP", "its coding-app registrations and skills"]
    if purge:
        removed.append("its downloaded runtimes")
    if forget:
        removed.append("saved campus sign-ins and Git tokens")
    kept = ["settings", "downloads", "course work"]
    if not forget:
        kept.insert(0, "campus sign-ins")
    console.print("Removes " + ", ".join(removed[:-1]) + " and " + removed[-1] + ".")
    console.print("Keeps your " + ", ".join(kept[:-1]) + " and " + kept[-1] + ".")
    try:
        return choose("Remove TUM MCP?", ((False, "Cancel"), (True, "Remove")))
    except (EOFError, KeyboardInterrupt):
        return False


def choose_extensions(
    *, installing: bool, json_output: bool = False, purge: bool = False, forget: bool = False
) -> tuple[ExtensionName, ...]:
    """Select optional workflows, or hand full removal back to the npm launcher."""
    if json_output or not interactive_terminal():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Use an interactive terminal or name lecture, audio-notes, "
            "video-notes or course-memory.",
        )
    rows = extension_rows()
    console = terminal_console()
    heading(console, "Install" if installing else "Uninstall")

    def selectable(state: State) -> bool | str:
        if state == State.FAILED:
            return "needs review"
        if installing:
            return True if state == State.DISABLED else "installed"
        if purge or forget:
            return "choose Everything for this cleanup"
        return True if state == State.ENABLED else "not installed"

    wide = console.width >= 70
    choices: list[tuple[str, str, State | None, bool | str]] = [
        (
            name.value,
            f"{label:<14} {fit(description, console, 14)}"
            if wide and installing and selectable(state) is True
            else label,
            None,
            selectable(state),
        )
        for name, label, state, description, _ in rows
    ]
    if not installing:
        choices.append(("all", "Everything (remove TUM MCP)", None, True))
    if not any(row[3] is True for row in choices):
        status_rows(console, [(label, state, status) for _, label, state, _, status in rows])
        if any(state == State.FAILED for _, _, state, _, _ in rows):
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "A workflow record is invalid (see above); fix or delete that file, then retry.",
            )
        console.print("All optional workflows are already installed. Nothing was changed.")
        return ()
    try:
        selected = select_many(
            "Which workflows do you want to add?" if installing else "What do you want to remove?",
            tuple(choices),
            exclusive="all" if not installing else None,
        )
    except (EOFError, KeyboardInterrupt):
        selected = None
    if not selected:
        console.print("Cancelled. Nothing was changed.")
        raise typer.Exit(130)
    if "all" in selected:
        import os

        if os.environ.get("TUM_MCP_NPM_LAUNCHER") != "1":
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Full removal runs through the npm command: run tum-mcp uninstall from npm.",
            )
        if not confirm_full_removal(purge=purge, forget=forget):
            console.print("Cancelled. Nothing was changed.")
            raise typer.Exit(130)
        raise typer.Exit(20)
    return tuple(ExtensionName(name) for name in selected)
