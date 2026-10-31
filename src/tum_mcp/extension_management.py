"""Shared extension selection for install, uninstall and doctor."""

import json
import sys
from enum import StrEnum
from typing import assert_never

import typer

from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import (
    lecture_installation,
    selection,
    set_audio_notes,
    set_video_notes,
    uninstall_lecture,
)
from tum_mcp.ui import State, heading, select_many, status_rows, terminal_console


class ExtensionName(StrEnum):
    LECTURE = "lecture"
    AUDIO_NOTES = "audio-notes"
    VIDEO_NOTES = "video-notes"


EXTENSIONS = tuple(ExtensionName)
LABELS = {
    "lecture": "Lecture",
    "audio-notes": "Audio Notes",
    "video-notes": "Video Notes",
}


def extension_rows() -> list[tuple[str, State, str]]:
    descriptions = {
        "lecture": "Prepare Lecture, transcripts and selected recording frames.",
        "audio-notes": "Create spoken lessons from prepared Study content.",
        "video-notes": "Create narrated, animated explainers from prepared Study content.",
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
                case unreachable:
                    assert_never(unreachable)
            detail = descriptions[name]
            if name == ExtensionName.VIDEO_NOTES and enabled:
                from tum_mcp.video_runtime import summary

                detail = f"{detail} {summary()}"
            rows.append((LABELS[name], State.ENABLED if enabled else State.DISABLED, detail))
        except CampusError as error:
            rows.append((LABELS[name], State.FAILED, error.message))
    return rows


def interactive_terminal() -> bool:
    return sys.stdin.isatty()


def remove_extensions(
    names: tuple[ExtensionName, ...], *, json_output: bool = False, show_heading: bool = True
) -> None:
    console = terminal_console()
    if not json_output and show_heading:
        heading(
            console,
            "Remove extensions",
            "Disable selected workflows; keep notes, sessions and custom files.",
        )
    reports = []
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
            case unreachable:
                assert_never(unreachable)
        needs_review |= review
        reports.append(report)
        if not json_output:
            status_rows(
                console,
                [
                    (
                        LABELS[name],
                        State.ACTION if review else State.DISABLED,
                        "Disabled. Customized client files need review."
                        if review
                        else "Workflow disabled; your materials and saved data were retained.",
                    )
                ],
            )
    if json_output:
        typer.echo(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2))
    else:
        console.print("Reload or restart configured clients to apply the change.")
    if needs_review:
        raise typer.Exit(2)


def choose_extensions(
    *, installing: bool, json_output: bool = False, full_only: bool = False
) -> tuple[ExtensionName, ...]:
    """Select optional workflows, or hand full removal back to the npm launcher."""
    if json_output or not interactive_terminal():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Use an interactive terminal or name lecture, audio-notes or video-notes.",
        )
    rows = extension_rows()
    console = terminal_console()
    heading(
        console,
        "Install" if installing else "Uninstall",
        "Choose optional workflows."
        if installing
        else "Choose All to apply the requested runtime or credential cleanup."
        if full_only
        else "Choose extensions, or All to remove TUM MCP and its managed client setup. "
        "Personal data is retained.",
    )
    choices = [
        (
            name.value,
            label,
            state,
            state == State.DISABLED if installing else state == State.ENABLED and not full_only,
        )
        for name, (label, state, _) in zip(EXTENSIONS, rows, strict=True)
    ]
    if not installing:
        choices.append(("all", "All — TUM MCP", State.ENABLED, True))
    if not any(row[3] for row in choices):
        status_rows(console, rows)
        if any(state == State.FAILED for _, state, _ in rows):
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Review the failed extension records locally before installing.",
            )
        console.print("All optional workflows are already installed. Nothing was changed.")
        return ()
    try:
        selected = select_many(
            "Install" if installing else "Uninstall",
            tuple(choices),
            exclusive="all" if not installing else None,
        )
    except (EOFError, KeyboardInterrupt):
        selected = None
    if not selected:
        console.print("Cancelled. No extensions were changed.")
        raise typer.Exit(130)
    if "all" in selected:
        import os

        if os.environ.get("TUM_MCP_NPM_LAUNCHER") != "1":
            raise CampusError(
                Code.ACTION_REQUIRED, "Use the npm tum-mcp command for full package removal."
            )
        raise typer.Exit(20)
    return tuple(ExtensionName(name) for name in selected)
