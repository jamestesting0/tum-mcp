"""Stable names for the study workflows and their retired predecessors."""

from typing import Final

CURRENT_SKILLS: Final = ("read-content", "init-study", "update-study", "prepare-study")
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
