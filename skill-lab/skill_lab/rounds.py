"""Rounds: one targeted weakness, its models, budget, variants, runs and judgements."""

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from skill_lab import LabError, models, paths, scenarios
from skill_lab.models import ModelSpec
from skill_lab.variants import Base, resolve_ref


def config_path(round_id: str) -> Path:
    return paths.round_dir(round_id) / "round.yaml"


def load(round_id: str) -> dict:
    path = config_path(round_id)
    if not path.is_file():
        raise LabError(f"No round {round_id!r}; create it with `lab round new`.")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def save(round_id: str, data: dict) -> None:
    path = config_path(round_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def base_of(data: dict) -> Base:
    return Base.from_dict(data["base"])


def composed_patch(round_id: str) -> str:
    record = paths.round_dir(round_id) / "variants" / "composed" / "variant.json"
    if not record.is_file():
        raise LabError(f"Round {round_id} has no composed variant to build on.")
    patches = json.loads(record.read_text(encoding="utf-8"))["spec"]["patches"]
    if not patches:
        raise LabError(f"Round {round_id}'s composed variant has no patch.")
    return patches[-1]["path"]


def validate_spec(spec: ModelSpec, role: str) -> None:
    models.validate(spec, role=role, profile_home=paths.profile_home(spec.host))


def new(
    round_id: str,
    *,
    scenario: str,
    confirm_scenario: str | None,
    author: str,
    judge: str,
    confirm_judges: list[str] | None,
    matrix: list[str],
    reason: str,
    base_ref: str | None,
    previous: str | None,
    baselines: list[str] | None = None,
    budget_runs: int = 10,
    budget_judges: int = 6,
    turn_timeout_min: int = 45,
) -> dict:
    if config_path(round_id).exists():
        raise LabError(f"Round {round_id} already exists.")
    for name in filter(None, (scenario, confirm_scenario)):
        scenarios.load(name)
    author_spec, judge_spec = ModelSpec.parse(author), ModelSpec.parse(judge)
    confirm = [ModelSpec.parse(t) for t in (confirm_judges or models.DEFAULT_CONFIRM_JUDGES)]
    extra = [ModelSpec.parse(text) for text in matrix]
    for spec in (author_spec, *extra):
        validate_spec(spec, "author")
    for spec in (judge_spec, *confirm):
        validate_spec(spec, "judge")
    if previous:
        prior = load(previous)
        base = Base(prior["base"]["ref"], [*prior["base"]["patches"], composed_patch(previous)])
    else:
        base = Base(resolve_ref(base_ref or "HEAD"))
    data = {
        "id": round_id,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "from": previous,
        "base": base.as_dict(),
        "scenario": scenario,
        "confirm_scenario": confirm_scenario,
        "roles": {"author": author_spec.as_dict(), "judge": judge_spec.as_dict()},
        "confirm_judges": [spec.as_dict() for spec in confirm],
        "matrix": [spec.as_dict() for spec in extra],
        # Earlier runs this round's candidates are judged against; the round does not rerun them.
        "baselines": checked_baselines(
            baselines if baselines is not None else inherited_baselines(previous)
        ),
        "budget": {
            "runs": budget_runs,
            "judge_sessions": budget_judges,
            "turn_timeout_min": turn_timeout_min,
        },
        "reason": reason,
    }
    save(round_id, data)
    return data


def inherited_baselines(previous: str | None) -> list[str]:
    """The previous round's result per author: its newest completed run of each author."""
    if not previous:
        return []
    newest: dict[str, dict] = {}
    for run in runs_of(previous):
        if run["status"] == "completed" and (
            run["author"] not in newest or run["started"] > newest[run["author"]]["started"]
        ):
            newest[run["author"]] = run
    return [f"{previous}/{run['id']}" for run in newest.values()]


def checked_baselines(references: list[str]) -> list[str]:
    for reference in references:
        if "/" not in reference:
            raise LabError(f"Name a baseline as ROUND/RUN, not {reference!r}.")
        source, run_id = reference.split("/", 1)
        run = next((item for item in runs_of(source) if item["id"] == run_id), None)
        if run is None or run["status"] != "completed":
            raise LabError(f"Baseline {reference} is not a completed run.")
    return list(references)


def set_baselines(round_id: str, references: list[str]) -> dict:
    data = load(round_id)
    data["baselines"] = checked_baselines(references)
    save(round_id, data)
    return data


def runs_of(round_id: str) -> list[dict]:
    root = paths.round_dir(round_id) / "runs"
    found = []
    for record in sorted(root.glob("*/run.json")) if root.is_dir() else []:
        found.append(json.loads(record.read_text(encoding="utf-8")))
    return found


def judgements_of(round_id: str) -> list[dict]:
    root = paths.round_dir(round_id) / "judge"
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (sorted(root.glob("*/result.json")) if root.is_dir() else [])
    ]


def check_budget(round_id: str, kind: str, adding: int = 1) -> None:
    data = load(round_id)
    if kind == "runs":
        # Count claimed folders too: a starting run has its folder before its record.
        root = paths.round_dir(round_id) / "runs"
        claimed = [path for path in root.iterdir() if path.is_dir()] if root.is_dir() else []
        used, limit = len(claimed), int(data["budget"]["runs"])
    else:
        used = sum(len(j.get("sessions", [])) for j in judgements_of(round_id))
        limit = int(data["budget"]["judge_sessions"])
    if used + adding > limit:
        raise LabError(
            f"Round {round_id} would use {used + adding} {kind} of its budget of {limit}; "
            "raise it in round.yaml if this is intended."
        )


def status_rows(round_id: str) -> list[dict]:
    rows = []
    for run in runs_of(round_id):
        metrics_path = paths.round_dir(round_id) / "runs" / run["id"] / "metrics.json"
        metrics = (
            json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.is_file() else {}
        )
        rows.append(
            {
                "run": run["id"],
                "variant": run["variant"],
                "author": run["author"],
                "status": run["status"],
                "turns": len(run.get("turns", [])),
                "minutes": run.get("minutes"),
                "delivered": metrics.get("delivered"),
                "inventory": (run.get("inventory_hash") or "")[:10],
                "human_review": (paths.round_dir(round_id) / "human" / f"{run['id']}.md").is_file(),
            }
        )
    return rows
