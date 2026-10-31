"""Host, model and effort choices per role, validated before any run starts."""

import json
from dataclasses import dataclass
from pathlib import Path

from skill_lab import LabError

HOSTS = ("claude", "codex")
CLAUDE_ALIASES = ("opus", "sonnet", "haiku", "fable")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
JUDGE_FORBIDDEN_EFFORTS = frozenset({"ultra"})
DEFAULT_CONFIRM_JUDGES = ("claude:claude-opus-5-5:xhigh", "codex:gpt-6.1-sol:xhigh")
DEFAULT_AUTHORS = {"claude": "claude:opus:medium", "codex": "codex:gpt-6.1-terra:xhigh"}


@dataclass(frozen=True)
class ModelSpec:
    host: str
    model: str
    effort: str

    @classmethod
    def parse(cls, text: str) -> "ModelSpec":
        text = DEFAULT_AUTHORS.get(text, text)
        parts = text.split(":")
        if len(parts) != 3 or not all(parts):
            raise LabError(f"Model spec {text!r} must be host:model:effort.")
        host, model, effort = parts
        if host not in HOSTS:
            raise LabError(f"Unknown host {host!r}; use one of {', '.join(HOSTS)}.")
        return cls(host, model, effort)

    def __str__(self) -> str:
        return f"{self.host}:{self.model}:{self.effort}"

    def as_dict(self) -> dict[str, str]:
        return {"host": self.host, "model": self.model, "effort": self.effort}

    @classmethod
    def from_dict(cls, value: dict[str, str]) -> "ModelSpec":
        return cls.parse(f"{value['host']}:{value['model']}:{value['effort']}")


def codex_models(cache: Path) -> dict[str, tuple[str, ...]]:
    if not cache.is_file():
        return {}
    data = json.loads(cache.read_text(encoding="utf-8"))
    return {
        model["slug"]: tuple(
            level["effort"] for level in model.get("supported_reasoning_levels", [])
        )
        for model in data.get("models", [])
        if model.get("slug")
    }


def codex_cache(profile_home: Path) -> Path:
    lab = profile_home / ".codex" / "models_cache.json"
    return lab if lab.is_file() else Path.home() / ".codex" / "models_cache.json"


def available(host: str, profile_home: Path) -> dict[str, tuple[str, ...]]:
    if host == "claude":
        return dict.fromkeys(CLAUDE_ALIASES, CLAUDE_EFFORTS)
    return codex_models(codex_cache(profile_home))


def validate(spec: ModelSpec, *, role: str, profile_home: Path) -> None:
    if role == "judge" and spec.effort in JUDGE_FORBIDDEN_EFFORTS:
        raise LabError(f"Effort {spec.effort!r} delegates work and is not allowed for judging.")
    if spec.host == "claude":
        if spec.model not in CLAUDE_ALIASES and not spec.model.startswith("claude-"):
            raise LabError(f"Claude model {spec.model!r} is neither an alias nor a claude-* name.")
        if spec.effort not in CLAUDE_EFFORTS:
            raise LabError(f"Claude effort must be one of {', '.join(CLAUDE_EFFORTS)}.")
        return
    models = codex_models(codex_cache(profile_home))
    if not models:
        raise LabError("No Codex model list found; log the Codex profile in and run it once.")
    if spec.model not in models:
        raise LabError(f"Codex model {spec.model!r} is not in the model list: {sorted(models)}.")
    if spec.effort not in models[spec.model]:
        raise LabError(f"{spec.model} supports efforts {models[spec.model]}, not {spec.effort!r}.")


def reported_matches(spec: ModelSpec, reported: str | None) -> bool | None:
    if not reported:
        return None
    if spec.host == "claude" and spec.model in CLAUDE_ALIASES:
        return spec.model in reported
    return reported == spec.model or reported.startswith(spec.model)
