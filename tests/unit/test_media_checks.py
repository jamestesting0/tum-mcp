"""The media check ids the review guide names are the ones the media gate accepts."""

import re
from importlib.resources import files

from tum_mcp.course.review.media import COMMON_CHECKS, PROFILE_CHECKS


def test_media_guide_names_exactly_the_checks_the_gate_accepts() -> None:
    guide = (files("tum_mcp.bundled") / "skills/review-course/references/media.md").read_text(
        encoding="utf-8"
    )
    shared = guide.split("## Shared checks", 1)[1].split("## Source-derived profiles", 1)[0]
    named: set[str] = set()
    for row in re.findall(r"^\| ([a-z_]+)(?: \([a-z]+\))? \| (.+) \|$", shared, re.MULTILINE):
        dimension, cells = row
        # A check is named before its colon or in a comma list; `listen` is the tool.
        named |= {f"{dimension}.{check}" for check in re.findall(r"`([a-z_]+)`(?=[:,])", cells)}
    profiles = guide.split("## Source-derived profiles", 1)[1].split("## Repair", 1)[0]
    named |= set(re.findall(r"`([a-z_]+\.[a-z_]+)`", profiles))
    assert named == COMMON_CHECKS | set().union(*PROFILE_CHECKS.values())
