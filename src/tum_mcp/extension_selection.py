"""Shared optional workflow selection and transactional managed-client activation."""

import re
from typing import Literal

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import config_dir, config_path

_FUTURE_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")


class ExtensionSelection(BaseModel):
    """Known workflows stay strict; boolean flags written by newer releases are preserved."""

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: Literal[1] = 1
    audio_notes: StrictBool = False
    video_notes: StrictBool = False
    course_memory: StrictBool = False

    @model_validator(mode="after")
    def future_flags(self) -> "ExtensionSelection":
        extra = self.model_extra or {}
        if len(extra) > 16 or any(
            _FUTURE_KEY.fullmatch(key) is None or type(value) is not bool
            for key, value in extra.items()
        ):
            raise ValueError("Unknown extension selections must be boolean flags.")
        return self

    def serialized(self) -> bytes:
        # Older runtimes reject unknown keys, so the newest flag is written only when enabled.
        exclude = {name for name in ("video_notes", "course_memory") if not getattr(self, name)}
        return self.model_dump_json(indent=2, exclude=exclude).encode()


def selection() -> ExtensionSelection:
    path = config_path() / "extensions.json"
    if not path.exists():
        return ExtensionSelection()
    try:
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError
        return ExtensionSelection.model_validate_json(path.read_bytes())
    except (OSError, ValueError, ValidationError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Invalid extension selection; review it locally."
        ) from None


def video_notes_enabled() -> bool:
    try:
        return selection().video_notes
    except CampusError:
        return False


def require_video_notes() -> None:
    if not video_notes_enabled():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Install the optional Video Notes extension with tum-mcp install video-notes.",
        )


FIELDS = {
    "audio-notes": "audio_notes",
    "video-notes": "video_notes",
    "course-memory": "course_memory",
}
SKILLS = {name: name for name in FIELDS}


def set_extension(
    name: Literal["audio-notes", "video-notes", "course-memory"], enabled: bool
) -> str:
    """Enable only after all clients preflight; disable before trying to prune files."""
    from tum_mcp.client_config import client_config_path, read_client_config
    from tum_mcp.client_installs import Write, commit_writes, prune_removed_folders
    from tum_mcp.clients import prepare_client
    from tum_mcp.skills import metadata, selected
    from tum_mcp.updates import installation_targets

    with FileLock(str(config_dir() / "client-install.lock")):
        previous = selection()
        path = config_path() / "extensions.json"
        before = path.read_bytes() if path.exists() else None
        field = FIELDS[name]
        desired = previous.model_copy(update={field: enabled})
        after = desired.serialized()
        if enabled:
            metadata(selected(SKILLS[name]))
        was_enabled = getattr(previous, field)
        if not enabled and was_enabled:
            commit_writes((Write(path, before, after),))
            before = after
        targets, issues = installation_targets()
        if issues:
            if not enabled:
                return "disabled_needs_review"
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Client installations need review before activation."
            )
        writes: list[Write] = []
        removed = []
        try:
            for client, host, home in targets:
                target = client_config_path(client, home, host=host)
                if read_client_config(target, for_update=True).mcpServers.get("tum") is None:
                    continue
                planned, deleted, _ = prepare_client(client, home, host=host, extensions=desired)
                writes.extend(planned)
                removed.append((home, deleted))
            if enabled:
                writes.append(Write(path, before, after))
            commit_writes(tuple(writes))
            for home, deleted in removed:
                prune_removed_folders(home, deleted)
        except (CampusError, OSError):
            if not enabled:
                return "disabled_needs_review"
            raise
        return "enabled" if enabled else "disabled"


def audio_notes_enabled() -> bool:
    try:
        return selection().audio_notes
    except CampusError:
        return False


def set_audio_notes(enabled: bool) -> str:
    return set_extension("audio-notes", enabled)


def set_video_notes(enabled: bool) -> str:
    return set_extension("video-notes", enabled)


def course_memory_enabled() -> bool:
    try:
        return selection().course_memory
    except CampusError:
        return False


def require_course_memory() -> None:
    if not course_memory_enabled():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Install the optional Course Memory extension with tum-mcp install course-memory.",
        )


def set_course_memory(enabled: bool) -> str:
    return set_extension("course-memory", enabled)
