"""Shared optional workflow selection and transactional managed-client activation."""

from typing import Literal

from filelock import FileLock
from pydantic import StrictBool, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen, config_dir, config_path


class ExtensionSelection(Frozen):
    schema_version: Literal[1] = 1
    studocu: StrictBool = False
    audio_notes: StrictBool = False


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


def studocu_enabled() -> bool:
    try:
        return selection().studocu
    except CampusError:
        return False


def set_extension(name: Literal["studocu", "audio-notes"], enabled: bool) -> str:
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
        field = "studocu" if name == "studocu" else "audio_notes"
        desired = previous.model_copy(update={field: enabled})
        after = desired.model_dump_json(indent=2).encode()
        if enabled and name == "studocu":
            try:
                from tum_mcp.moodle.protocol import StrictMCPServer
                from tum_mcp.studocu.server import register

                register(StrictMCPServer("Studocu activation preflight"))
            except Exception:
                raise CampusError(
                    Code.CAPABILITY_UNSUPPORTED,
                    "Studocu tools could not be prepared; activation was not changed.",
                ) from None
        if enabled:
            metadata(selected("sync-studocu" if name == "studocu" else "audio-notes"))
        was_enabled = previous.studocu if name == "studocu" else previous.audio_notes
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


def set_studocu(enabled: bool) -> str:
    return set_extension("studocu", enabled)


def audio_notes_enabled() -> bool:
    try:
        return selection().audio_notes
    except CampusError:
        return False


def set_audio_notes(enabled: bool) -> str:
    return set_extension("audio-notes", enabled)
