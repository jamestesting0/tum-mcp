"""The review checks: one definition per check, shared by the author's checklist and reviewers."""

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

PROFILES = (
    "study-unit",
    "exercise",
    "exam-pattern",
    "exam-sheet",
    "exam-mock-question",
    "lecture-entry",
    "lecture-selection",
    "course",
)


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    dimension: str
    rule: str
    passing: str
    failing: str
    profiles: tuple[str, ...]
    scope: str
    version: int
    default_fail: bool = False
    teaching: bool = False
    decided_by: str | None = None

    def brief(self) -> dict[str, object]:
        return {
            "check": self.id,
            "rule": self.rule,
            "pass": self.passing,
            "fail": self.failing,
            **({"default_fail": True} if self.default_fail else {}),
        }


@cache
def registry() -> dict:
    path = files("tum_mcp.bundled").joinpath("review/checks.json")
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def checks() -> dict[str, Check]:
    return {
        entry["id"]: Check(
            id=entry["id"],
            dimension=entry["dimension"],
            rule=entry["rule"],
            passing=entry["pass"],
            failing=entry["fail"],
            profiles=tuple(entry["profiles"]),
            scope=entry["scope"],
            version=entry["version"],
            default_fail=entry.get("default_fail", False),
            teaching=entry.get("teaching", False),
            decided_by=entry.get("decided_by"),
        )
        for entry in registry()["checks"]
    }


def for_profile(profile: str) -> tuple[Check, ...]:
    return tuple(check for check in checks().values() if profile in check.profiles)


def judged(profile: str) -> tuple[Check, ...]:
    """The checks a reviewer answers; the others are decided by a code flag."""
    return tuple(check for check in for_profile(profile) if check.decided_by is None)


def dimensions(profile: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(check.dimension for check in for_profile(profile)))
