"""Student scenarios: ordered messages, canned replies and the skills each turn relies on."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from skill_lab import LabError, paths

SKILL_PREFIX = "src/tum_mcp/bundled/skills/"
MAX_REPLIES_PER_TURN = 2
TAIL_PARAGRAPHS = 6
CLOSING_PARAGRAPHS = 2
ADDRESSED = re.compile(r"\b(?:you|your|should i|shall i|do i|may i)\b", re.IGNORECASE)
QUESTION = re.compile(r"[^.!?\n]*\?(?=[*_`)\"']*(?:\s|$))")
REQUEST = re.compile(
    r"[^.!?\n]*\b(?:please (?:choose|select|pick|confirm|tell|reply|answer)|tell me|let me know"
    r"|once you (?:choose|confirm|tell|select|pick))\b[^.!?\n]*",
    re.IGNORECASE,
)


@dataclass
class Turn:
    say: str
    skills: list[str] = field(default_factory=list)
    # Workspaces this turn only adds to (a practice exam beside restored patterns).
    extends: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    id: str
    turns: list[Turn]
    replies: dict[str, str] = field(default_factory=dict)

    def reply_to(self, text: str) -> str | None:
        asked = question_text(text).lower()
        for key, answer in self.replies.items():
            if key != "default" and key.lower() in asked:
                return answer
        return self.replies.get("default")


def question_text(text: str) -> str:
    paragraphs = [part for part in text.strip().split("\n\n") if part.strip()]
    closing = "\n".join(paragraphs[-CLOSING_PARAGRAPHS:])
    tail = "\n".join(paragraphs[-TAIL_PARAGRAPHS:])
    found = [m.group(0).strip() for m in QUESTION.finditer(closing)]
    found += [m.group(0).strip() for m in QUESTION.finditer(tail) if ADDRESSED.search(m.group(0))]
    found += [m.group(0).strip() for m in REQUEST.finditer(tail)]
    return " ".join(dict.fromkeys(found))


def asks_student(text: str) -> bool:
    return bool(question_text(text))


def parse(data: dict, source: str) -> Scenario:
    if not isinstance(data, dict) or not data.get("id") or not data.get("turns"):
        raise LabError(f"Scenario {source} needs an id and at least one turn.")
    turns = []
    for item in data["turns"]:
        if isinstance(item, str):
            turns.append(Turn(item))
        elif isinstance(item, dict) and isinstance(item.get("say"), str):
            turns.append(
                Turn(
                    item["say"],
                    [str(s) for s in item.get("skills", [])],
                    [str(s) for s in item.get("extends", [])],
                )
            )
        else:
            raise LabError(f"Scenario {source} has a turn that is neither text nor say/skills.")
    replies = {str(k): str(v) for k, v in (data.get("replies") or {}).items()}
    return Scenario(str(data["id"]), turns, replies)


def load(scenario_id: str) -> Scenario:
    tracked = paths.SCENARIOS / f"{scenario_id}.yaml"
    if not tracked.is_file():
        raise LabError(f"No scenario {scenario_id!r} in {paths.SCENARIOS}.")
    data = yaml.safe_load(tracked.read_text(encoding="utf-8"))
    override = paths.state() / "scenarios" / f"{scenario_id}.yaml"
    if override.is_file():
        local = yaml.safe_load(override.read_text(encoding="utf-8")) or {}
        if "turns" in local:
            data["turns"] = local["turns"]
        data["replies"] = {**(data.get("replies") or {}), **(local.get("replies") or {})}
    return parse(data, str(tracked))


def available() -> list[str]:
    return sorted(path.stem for path in Path(paths.SCENARIOS).glob("*.yaml"))


# Skills that bind or build the course workspaces a checkpoint restores.
AUTHORING = frozenset(
    {"sync-course", "prepare-study", "prepare-exercises", "prepare-exams", "prepare-lecture"}
)


# The app workspace each prepare skill builds. sync-course refreshes sources and the
# handbook but never writes a workspace, so it may follow a restore.
BUILDS = {
    "prepare-study": "study",
    "prepare-exercises": "exercises",
    "prepare-exams": "exam",
    "prepare-lecture": "lectures",
}


def drift_refusal(
    scenario: Scenario, start_turn: int, restored: frozenset[str] = frozenset(BUILDS.values())
) -> str | None:
    """Changed code is acceptable only when the later turns read the restored workspaces and
    never rebuild them, so the restored content stays the same input for every variant. A
    later turn may build a workspace the checkpoint does not have, or add to one it declares in
    `extends`."""
    later = scenario.turns[start_turn:]
    if any(not turn.skills for turn in later):
        return "A later turn does not list its skills, so it may rebuild restored content."
    rebuilt = sorted(
        {
            skill
            for turn in later
            for skill in set(turn.skills) & AUTHORING
            if skill in BUILDS and BUILDS[skill] in restored and BUILDS[skill] not in turn.extends
        }
    )
    if rebuilt:
        return f"Later turns use {', '.join(rebuilt)}, which rebuild restored content."
    return None


def checkpoint_refusal(scenario: Scenario, start_turn: int, touched: list[str]) -> str | None:
    if start_turn <= 0:
        return None
    earlier = scenario.turns[:start_turn]
    if any(not turn.skills for turn in earlier):
        return "An earlier turn does not list its skills, so reuse cannot be proven safe."
    used = {skill for turn in earlier for skill in turn.skills}
    for path in touched:
        if not path.startswith(SKILL_PREFIX):
            return f"The variant changes code ({path}) that earlier turns may have used."
        if path[len(SKILL_PREFIX) :].split("/", 1)[0] in used:
            return f"The variant changes {path}, which an earlier turn used."
    return None
