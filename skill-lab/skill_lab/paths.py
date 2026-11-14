"""Where the lab's tracked files and its local, gitignored state live."""

import os
import re
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


def profile_name(host: str) -> str:
    """The host's profile. `SKILL_LAB_SLOT` names a separate copy, so several trials of one
    host can run side by side, each in its own profile."""
    slot = os.environ.get("SKILL_LAB_SLOT")
    if not slot:
        return host
    if not re.fullmatch(r"[a-z0-9]{1,12}", slot):
        raise ValueError("SKILL_LAB_SLOT is 1-12 lowercase letters or digits.")
    return f"{host}-{slot}"


def profile_home(host: str) -> Path:
    return state() / "profiles" / profile_name(host) / ("config" if host == "claude" else "home")
