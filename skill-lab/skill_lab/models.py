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
DEFAULT_AUTHORS = {"claude": "claude:opus:medium", "codex": "codex:gpt-6.1-terra:high:fast"}


@dataclass(frozen=True)
class ModelSpec:
    host: str
    model: str
    effort: str
    tier: str | None = None

    @classmethod
    def parse(cls, text: str) -> "ModelSpec":
        text = DEFAULT_AUTHORS.get(text, text)
        parts = text.split(":")
        if len(parts) not in (3, 4) or not all(parts):
            raise LabError(f"Model spec {text!r} must be host:model:effort[:fast].")
        host, model, effort = parts[:3]
        if host not in HOSTS:
            raise LabError(f"Unknown host {host!r}; use one of {', '.join(HOSTS)}.")
        tier = parts[3] if len(parts) == 4 else None
        if tier is not None and tier != "fast":
            raise LabError(f"Unknown speed tier {tier!r}; use fast or omit the tier.")
        if tier and host != "codex":
            raise LabError("The fast tier is supported only for Codex.")
        return cls(host, model, effort, tier)

    def __str__(self) -> str:
        base = f"{self.host}:{self.model}:{self.effort}"
        return f"{base}:{self.tier}" if self.tier else base

    def as_dict(self) -> dict[str, str]:
        result = {"host": self.host, "model": self.model, "effort": self.effort}
        if self.tier:
            result["tier"] = self.tier
        return result

    @classmethod
    def from_dict(cls, value: dict[str, str]) -> "ModelSpec":
        base = f"{value['host']}:{value['model']}:{value['effort']}"
        return cls.parse(f"{base}:{value['tier']}" if "tier" in value else base)


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
    if spec.tier == "fast":
        data = json.loads(codex_cache(profile_home).read_text(encoding="utf-8"))
        model = next(item for item in data["models"] if item.get("slug") == spec.model)
        if not any(tier.get("id") == "priority" for tier in model.get("service_tiers", [])):
            raise LabError(f"Codex model {spec.model!r} does not support the fast priority tier.")


def reported_matches(spec: ModelSpec, reported: str | None) -> bool | None:
    if not reported:
        return None
    if spec.host == "claude" and spec.model in CLAUDE_ALIASES:
        return spec.model in reported
    return reported == spec.model or reported.startswith(spec.model)
