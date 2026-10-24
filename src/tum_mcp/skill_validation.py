"""Structural skill checks. Activation quality requires separate host/model trials."""

import re

import anyio
import yaml
from pydantic import Field

from tum_mcp.settings import Frozen
from tum_mcp.skills import bundled, metadata, selected


class ValidationReport(Frozen):
    checked_skills: tuple[str, ...]
    errors: tuple[str, ...]
    characters: int
    activation_evaluated: bool = False
    precision: float | None = None
    recall: float | None = None


def validate_skills() -> ValidationReport:
    from tum_mcp.server import server

    registered = {tool.name for tool in anyio.run(server.list_tools)}
    checked: list[str] = []
    errors: list[str] = []
    characters = 0
    for source in sorted(bundled().iterdir()):
        if not source.is_dir():
            continue
        chosen = selected(source.name)
        info = metadata(chosen)
        checked.append(info.name)
        content = (chosen / "SKILL.md").read_text()
        characters += len(content)
        for tool in re.findall(r"`((?:moodle|tum|zulip|artemis)_[a-z0-9_]+)`", content):
            if tool not in registered:
                errors.append(f"{info.name}: unregistered tool {tool}")
        if info.name == "tum-artemis-submit":
            policy_file = chosen / "agents/openai.yaml"
            if not policy_file.is_file():
                errors.append(f"{info.name}: missing explicit-invocation policy")
            else:
                policy = yaml.safe_load(policy_file.read_text())
                if policy.get("policy", {}).get("allow_implicit_invocation") is not False:
                    errors.append(f"{info.name}: implicit submission invocation enabled")
    return ValidationReport(
        checked_skills=tuple(checked), errors=tuple(errors), characters=characters
    )


class Trial(Frozen):
    case_id: str
    expected_skill: str | None
    selected_skill: str | None
    forbidden_effects: tuple[str, ...] = ()
    host: str
    host_version: str
    model: str
    trace_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
