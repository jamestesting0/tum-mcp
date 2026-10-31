"""Blind judging: anonymized outputs, cited sources and the rubric, scored by a pinned model."""

import hashlib
import json
import random
import re
import shutil
from pathlib import Path

from skill_lab import LabError, hosts, models, paths, rounds
from skill_lab.models import ModelSpec

DIMENSIONS = (
    "correctness",
    "coverage",
    "clarity",
    "cognitive_load",
    "representation",
    "practice",
    "intuition",
)
RUBRIC_FILES = ("rubric.md", "logic.md", "text.md", "visuals.md", "interaction.md", "intuition.md")
JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
# The judge compares only workspaces both runs built; the others are named, not judged.
WORKSPACE_FILES = {
    "content.json": "Study",
    "exercises.json": "Exercises",
    "exam.json": "Exam",
    "lectures.json": "Lecture",
}


def find_run(round_id: str, reference: str) -> dict | None:
    """A run of this round by id, or of an earlier round as ROUND/RUN."""
    source, run_id = reference.split("/", 1) if "/" in reference else (round_id, reference)
    return next((run for run in rounds.runs_of(source) if run["id"] == run_id), None)


def default_pairs(round_id: str) -> list[list[str]]:
    """Each baseline against this round's newest completed run by the same author."""
    config = rounds.load(round_id)
    pairs = []
    for reference in config.get("baselines") or []:
        baseline = find_run(round_id, reference)
        if baseline is None:
            raise LabError(f"Baseline {reference} does not exist.")
        latest = [
            run
            for run in rounds.runs_of(round_id)
            if run["author"] == baseline["author"] and run["status"] == "completed"
        ]
        if not latest:
            raise LabError(
                f"No completed run by {baseline['author']} to judge against {reference}."
            )
        pairs.append([reference, max(latest, key=lambda run: run["started"])["id"]])
    if not pairs:
        raise LabError("The round names no baselines; give --pairs left:right or set baselines.")
    return pairs


def rubric_references(run: dict) -> Path:
    repo = paths.round_dir(run["round"]) / "variants" / run["variant"] / "repo"
    return repo / "src/tum_mcp/bundled/skills/review-course/references"


def copy_sources(runs: list[dict], destination: Path) -> bool:
    """Give the judge every material either run read; report whether they read the same."""
    hashes = {run.get("inventory_hash") for run in runs}
    for run in runs:
        project = paths.round_dir(run["round"]) / "runs" / run["id"] / "workspace"
        materials = project / str(run.get("project")) / "materials"
        if run.get("project") and materials.is_dir():
            shutil.copytree(materials, destination, dirs_exist_ok=True)
    return len(hashes) == 1


def assign_ids(pair_key: str) -> dict[str, str]:
    seed = int(hashlib.sha256(pair_key.encode()).hexdigest()[:12], 16)
    order = ["left", "right"]
    random.Random(seed).shuffle(order)  # noqa: S311 - reproducible shuffle, not security
    return {"A": order[0], "B": order[1]}


def pick_run(
    round_id: str, reference: str, *, confirm: bool, author: str, scenario: str | None
) -> dict:
    runs = rounds.runs_of(round_id)
    named = find_run(round_id, reference)
    if named:
        if named["status"] != "completed":
            raise LabError(f"Run {reference} is {named['status']}, not completed.")
        return named
    candidates = [
        run
        for run in runs
        if run["variant"] == reference
        and run["status"] == "completed"
        and bool(run.get("confirm")) == confirm
        and run["author"] == author
        and (scenario is None or run["scenario"] == scenario)
    ]
    if not candidates:
        raise LabError(
            f"No completed {'confirmation ' if confirm else ''}run of {reference} by {author}"
            + (f" on {scenario}" if scenario else "")
            + "; name runs directly, for example base-2:dom-1."
        )
    return max(candidates, key=lambda run: run["started"])


def copy_candidate(run: dict, destination: Path) -> None:
    run_dir = paths.round_dir(run["round"]) / "runs" / run["id"]
    project = run_dir / "workspace" / run["project"] if run.get("project") else None
    destination.mkdir(parents=True)
    if project is None:
        (destination / "NO_PROJECT.txt").write_text("This run produced no course project.\n")
        return
    for relative in ("app", ".tum-mcp/visuals"):
        source = project / relative
        if source.is_dir():
            shutil.copytree(source, destination / relative.replace(".tum-mcp/", ""))


def build_packet(pair_key: str, left: dict, right: dict, packet: Path) -> dict:
    ids = assign_ids(pair_key)
    if packet.exists():
        shutil.rmtree(packet)
    runs = {"left": left, "right": right}
    for letter, side in ids.items():
        copy_candidate(runs[side], packet / "candidates" / letter)
    apps = {letter: packet / "candidates" / letter / "app" for letter in ids}
    unjudged = {}
    for name, workspace in WORKSPACE_FILES.items():
        built = [letter for letter, app in apps.items() if (app / name).is_file()]
        if len(built) == 1:
            unjudged[workspace] = runs[ids[built[0]]]["id"]
            (apps[built[0]] / name).unlink()
    # The bundled data repeats every workspace, including any left out above.
    for app in apps.values():
        (app / "data.mjs").unlink(missing_ok=True)
    same_materials = copy_sources([left, right], packet / "sources")
    # The rubric comes from the reference run's variant, in whichever round it ran.
    references = rubric_references(left)
    (packet / "rubric").mkdir(parents=True)
    for name in RUBRIC_FILES:
        if (references / name).is_file():
            shutil.copy2(references / name, packet / "rubric" / name)
    return {"ids": ids, "unjudged": unjudged, "same_materials": same_materials}


def parse_verdict(text: str) -> dict:
    blocks = JSON_BLOCK.findall(text)
    if not blocks:
        raise LabError("The judge did not return a ```json verdict block.")
    verdict = json.loads(blocks[-1])
    for key in ("scores", "preference", "overall"):
        if key not in verdict:
            raise LabError(f"The judge verdict lacks {key!r}.")
    if verdict["overall"] not in {"A", "B", "tie"}:
        raise LabError("The judge verdict's overall must be A, B or tie.")
    return verdict


def unblind(verdict: dict, ids: dict[str, str], names: dict[str, str]) -> dict:
    def name(letter: str) -> str:
        return names[ids[letter]] if letter in ids else letter

    return {
        "overall": name(verdict["overall"]),
        "preference": {dim: name(str(v)) for dim, v in verdict["preference"].items()},
        "scores": {name(letter): scores for letter, scores in verdict["scores"].items()},
        "why": verdict.get("why", ""),
    }


def judge_pair(
    round_id: str,
    left_variant: str,
    right_variant: str,
    *,
    confirm: bool = False,
    judges: list[ModelSpec] | None = None,
) -> dict:
    config = rounds.load(round_id)
    if judges is None:
        judges = (
            [ModelSpec.from_dict(item) for item in config["confirm_judges"]]
            if confirm
            else [ModelSpec.from_dict(config["roles"]["judge"])]
        )
    for spec in judges:
        models.validate(spec, role="judge", profile_home=paths.profile_home(spec.host))
    rounds.check_budget(round_id, "judge_sessions", len(judges))
    author = str(ModelSpec.from_dict(config["roles"]["author"]))
    left = pick_run(round_id, left_variant, confirm=confirm, author=author, scenario=None)
    right = pick_run(round_id, right_variant, confirm=confirm, author=left["author"], scenario=None)
    if left["author"] != right["author"]:
        raise LabError("Judged runs must share the author model.")
    # A baseline from an earlier round keeps its round in its name.
    label = {
        run["id"]: f"{run['round']}/{run['id']}" if run["round"] != round_id else run["id"]
        for run in (left, right)
    }
    left_variant, right_variant = left["variant"], right["variant"]
    if left_variant == right_variant or left["round"] != right["round"]:
        left_variant, right_variant = label[left["id"]], label[right["id"]]
    pair_key = f"{round_id}|{label[left['id']]}|{label[right['id']]}|{int(confirm)}"
    pair_id = f"{'confirm-' if confirm else ''}{label[left['id']]}-vs-{right['id']}".replace(
        "/", "-"
    )
    directory = paths.round_dir(round_id) / "judge" / pair_id
    packet = directory / "packet"
    built = build_packet(pair_key, left, right, packet)
    ids = built["ids"]
    names = {"left": left_variant, "right": right_variant}
    prompt = (paths.PROMPTS / "judge.md").read_text(encoding="utf-8")
    prompt = prompt.replace("{dimensions}", ", ".join(DIMENSIONS))
    timeout = int(config["budget"]["turn_timeout_min"]) * 60
    sessions = []
    for spec in judges:
        home = paths.profile_home(spec.host)
        environment = hosts.clean_environment({}, home, None, spec.host)
        result = hosts.run_turn(
            spec,
            prompt,
            workspace=packet,
            environment=environment,
            session=None,
            timeout=timeout,
            raw=directory / f"raw-{spec.host}.jsonl",
            judge=True,
        )
        entry: dict = {
            "judge": str(spec),
            "model_reported": result.model_reported,
            "matches": models.reported_matches(spec, result.model_reported),
        }
        if result.is_error:
            entry["error"] = result.error
        else:
            try:
                entry["verdict"] = unblind(parse_verdict(result.text), ids, names)
            except (LabError, ValueError) as error:
                entry["error"] = str(error)
        sessions.append(entry)
    winners = [s["verdict"]["overall"] for s in sessions if "verdict" in s]
    outcome = {
        "pair": pair_id,
        "confirm": confirm,
        "left": {"variant": left_variant, "run": label[left["id"]], "scenario": left["scenario"]},
        "right": {
            "variant": right_variant,
            "run": label[right["id"]],
            "scenario": right["scenario"],
        },
        "author": left["author"],
        "unjudged": built["unjudged"],
        "same_materials": built["same_materials"],
        "ids": ids,
        "sessions": sessions,
        "all_prefer_right": bool(winners)
        and len(winners) == len(sessions)
        and all(w == right_variant for w in winners),
    }
    (directory / "result.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    return outcome


def parse_review(text: str) -> dict:
    blocks = JSON_BLOCK.findall(text)
    if not blocks:
        raise LabError("The reviewer did not return a ```json block.")
    review = json.loads(blocks[-1])
    for key in ("scores", "findings"):
        if key not in review:
            raise LabError(f"The review lacks {key!r}.")
    return review


def other_host_reviewer(config: dict, author_host: str) -> ModelSpec:
    for item in config.get("confirm_judges") or []:
        spec = ModelSpec.from_dict(item)
        if spec.host != author_host:
            return spec
    raise LabError("The round has no confirmation judge on the other host; pass --judge.")


def review_run(round_id: str, run_id: str, *, judges: list[ModelSpec] | None = None) -> dict:
    config = rounds.load(round_id)
    run = pick_run(round_id, run_id, confirm=False, author="", scenario=None)
    if judges is None:
        judges = [other_host_reviewer(config, run["author"].split(":", 1)[0])]
    for spec in judges:
        models.validate(spec, role="judge", profile_home=paths.profile_home(spec.host))
    rounds.check_budget(round_id, "judge_sessions", len(judges))
    directory = paths.round_dir(round_id) / "judge" / f"review-{run_id}"
    packet = directory / "packet"
    if packet.exists():
        shutil.rmtree(packet)
    copy_candidate(run, packet / "candidates" / "A")
    copy_sources([run], packet / "sources")
    references = rubric_references(run)
    (packet / "rubric").mkdir(parents=True)
    for name in RUBRIC_FILES:
        if (references / name).is_file():
            shutil.copy2(references / name, packet / "rubric" / name)
    prompt = (paths.PROMPTS / "review.md").read_text(encoding="utf-8")
    prompt = prompt.replace("{dimensions}", ", ".join(DIMENSIONS))
    timeout = int(config["budget"]["turn_timeout_min"]) * 60
    sessions = []
    for spec in judges:
        result = hosts.run_turn(
            spec,
            prompt,
            workspace=packet,
            environment=hosts.clean_environment({}, paths.profile_home(spec.host), None, spec.host),
            session=None,
            timeout=timeout,
            raw=directory / f"raw-{spec.host}.jsonl",
            judge=True,
        )
        entry: dict = {
            "judge": str(spec),
            "model_reported": result.model_reported,
            "matches": models.reported_matches(spec, result.model_reported),
        }
        if result.is_error:
            entry["error"] = result.error
        else:
            try:
                entry["review"] = parse_review(result.text)
            except (LabError, ValueError) as error:
                entry["error"] = str(error)
        sessions.append(entry)
    outcome = {"review": run_id, "author": run["author"], "sessions": sessions}
    (directory / "result.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    return outcome
