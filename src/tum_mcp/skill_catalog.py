"""Stable names for the study workflows and their retired predecessors."""

from typing import Final

CURRENT_SKILLS: Final = (
    "read-content",
    "sync-course",
    "prepare-study",
    "prepare-exercises",
    "audio-notes",
    "publish-course",
)
OPTIONAL_SKILLS: Final = ("prepare-lecture",)
BUNDLED_SKILLS: Final = (*CURRENT_SKILLS, *OPTIONAL_SKILLS)


def active_skills() -> tuple[str, ...]:
    from tum_mcp.extensions import lecture_enabled

    return BUNDLED_SKILLS if lecture_enabled() else CURRENT_SKILLS


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
    }
)
