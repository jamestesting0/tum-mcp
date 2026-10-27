"""Explicit optional Lecture installation; base setup stays unchanged."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from filelock import FileLock, Timeout
from pydantic import AwareDatetime, Field, JsonValue

from tum_mcp import __version__
from tum_mcp.errors import CampusError, Code
from tum_mcp.extension_selection import audio_notes_enabled as audio_notes_enabled
from tum_mcp.extension_selection import selection as selection
from tum_mcp.extension_selection import set_audio_notes as set_audio_notes
from tum_mcp.extension_selection import set_studocu as set_studocu
from tum_mcp.extension_selection import set_video_notes as set_video_notes
from tum_mcp.extension_selection import studocu_enabled as studocu_enabled
from tum_mcp.extension_selection import video_notes_enabled as video_notes_enabled
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen, config_dir, config_path

if TYPE_CHECKING:
    from tum_mcp.lecture_processing.runtime import RuntimeStatus
    from tum_mcp.updates import UpdateSummary


class LectureReport(TypedDict):
    extension: str
    enabled: bool
    clients: "UpdateSummary"
    recognition: NotRequired[dict[str, JsonValue]]
    preserved: NotRequired[str]
    next_step: NotRequired[str]


class LectureInstallation(Frozen):
    schema_version: Literal[1] = 1
    enabled: bool
    installed_at: AwareDatetime
    package_version: str = Field(max_length=50)
    asr_requested: bool = True


def lecture_installation(*, strict: bool = False) -> LectureInstallation | None:
    path = config_path() / "lecture-extension.json"
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError("unsafe extension record")
        return LectureInstallation.model_validate_json(path.read_bytes())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        if strict:
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Lecture installation record needs local review; existing files were preserved.",
            ) from None
        return None


def lecture_enabled() -> bool:
    value = lecture_installation()
    return value is not None and value.enabled


def require_lecture() -> None:
    if not lecture_enabled():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Install the optional Lecture extension with tum-mcp install lecture.",
        )


def prepare_recognizer(requested: bool) -> "RuntimeStatus":
    from tum_mcp.lecture_processing.runtime import install, status

    current = status()
    if requested and current.supported and not current.installed:
        return install()
    return current


def install_lecture(*, asr: bool = True) -> LectureReport:
    from tum_mcp.updates import refresh_clients

    try:
        with FileLock(str(config_dir() / "lecture-extension.lock"), timeout=0):
            previous = lecture_installation(strict=True)
            capability = prepare_recognizer(asr)
            selected = LectureInstallation(
                enabled=True,
                installed_at=previous.installed_at
                if previous and previous.enabled
                else datetime.now(UTC),
                package_version=__version__,
                asr_requested=asr,
            )
            private_write(
                config_dir() / "lecture-extension.json", selected.model_dump_json(indent=2).encode()
            )
            clients = refresh_clients()
            return {
                "extension": "lecture",
                "enabled": True,
                "recognition": capability.model_dump(mode="json"),
                "clients": clients,
                "next_step": "Restart clients to load Prepare Lecture and TUM-Live tools.",
            }
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Another process is changing the Lecture extension."
        ) from None


def uninstall_lecture() -> LectureReport:
    from tum_mcp.updates import refresh_clients

    try:
        with FileLock(str(config_dir() / "lecture-extension.lock"), timeout=0):
            previous = lecture_installation(strict=True)
            if previous is None or not previous.enabled:
                return {
                    "extension": "lecture",
                    "enabled": False,
                    "clients": {"updated": 0, "needs_review": 0, "clients": []},
                }
            disabled = previous.model_copy(update={"enabled": False})
            private_write(
                config_dir() / "lecture-extension.json", disabled.model_dump_json(indent=2).encode()
            )
            return {
                "extension": "lecture",
                "enabled": False,
                "clients": refresh_clients(),
                "preserved": "Notes, evidence, saved sessions, model caches and customized files.",
                "next_step": "Reload/restart configured coding clients.",
            }
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Another process is changing the Lecture extension."
        ) from None
