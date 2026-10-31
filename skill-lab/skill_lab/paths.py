"""Where the lab's tracked files and its local, gitignored state live."""

import os
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
PROMPTS = LAB / "prompts"
SCENARIOS = LAB / "scenarios"
LEDGER = LAB / "ledger.md"


def state() -> Path:
    return Path(os.environ.get("SKILL_LAB_STATE") or REPO / ".omo" / "skill-lab")


def workspaces() -> Path:
    return Path(os.environ.get("SKILL_LAB_WORKSPACES") or Path.home() / ".skill-lab" / "workspaces")


def rounds() -> Path:
    return state() / "rounds"


def round_dir(round_id: str) -> Path:
    return rounds() / round_id


def profile_home(host: str) -> Path:
    return state() / "profiles" / host / ("config" if host == "claude" else "home")
