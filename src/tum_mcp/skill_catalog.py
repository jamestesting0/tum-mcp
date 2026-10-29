"""Stable names for the study workflows and their retired predecessors."""

from typing import Final

from tum_mcp.errors import CampusError
from tum_mcp.extension_selection import ExtensionSelection, selection

CURRENT_SKILLS: Final = (
    "read-content",
    "sync-course",
    "prepare-study",
    "prepare-exercises",
    "prepare-exams",
    "review-course",
    "publish-course",
)
OPTIONAL_SKILLS: Final = ("prepare-lecture", "audio-notes", "video-notes")
BUNDLED_SKILLS: Final = (*CURRENT_SKILLS, *OPTIONAL_SKILLS)


def active_skills(*, extensions: ExtensionSelection | None = None) -> tuple[str, ...]:
    from tum_mcp.extensions import lecture_enabled

    try:
        chosen = selection() if extensions is None else extensions
    except CampusError:
        chosen = ExtensionSelection()

    active = list(CURRENT_SKILLS)
    if lecture_enabled():
        active.append("prepare-lecture")
    if chosen.audio_notes:
        active.append("audio-notes")
    if chosen.video_notes:
        active.append("video-notes")
    return tuple(active)


LEGACY_SKILLS: Final = dict.fromkeys(
    (
        "tum-moodle-study",
        "tum-artemis-prepare",
        "tum-artemis-feedback",
        "tum-artemis-local-fix",
        "tum-artemis-submit",
        "tum-zulip-research",
        "tum-zulip-catch-up",
        "tum-moodle",
        "tum-artemis",
        "tum-zulip",
    ),
    "read-content",
)

LEGACY_SKILLS.update(
    {
        "init-study": "sync-course",
        "update-study": "sync-course",
        "sync-study": "sync-course",
        "publish-study": "publish-course",
        "sync-studocu": "sync-course",
    }
)
