import re
from pathlib import Path

from tum_mcp.course.review import registry
from tum_mcp.course.review.models import INVARIANT_FLAGS, RULED_FLAGS

DOC = Path(__file__).parents[2] / "docs/content-standards.md"


def enforcement() -> set[str]:
    rows = [
        line.split("|")
        for line in DOC.read_text(encoding="utf-8").splitlines()
        if line.startswith("| ")
    ]
    return {name for row in rows if len(row) > 3 for name in re.findall(r"`([a-z_.]+)`", row[3])}


def test_the_standards_name_only_existing_checks_and_every_flag_has_a_standard() -> None:
    named = enforcement()
    checks = set(registry.checks())
    flags = set(INVARIANT_FLAGS) | set(RULED_FLAGS)
    assert {name for name in named if "." in name} <= checks
    assert {name for name in named if "." not in name} <= flags
    assert flags <= named
