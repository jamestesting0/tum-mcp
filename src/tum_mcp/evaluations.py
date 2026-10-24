"""Score supplied host/model trials against a held-out activation corpus."""

from importlib.resources import files
from pathlib import Path

from pydantic import RootModel

from tum_mcp.errors import CampusError, Code
from tum_mcp.parsing import decode
from tum_mcp.settings import Frozen
from tum_mcp.skill_validation import Trial


class ActivationCase(Frozen):
    id: str
    target_skill: str
    prompt: str
    context: str
    partition: str
    expected_skill: str | None


class Corpus(RootModel[tuple[ActivationCase, ...]]):
    pass


class Score(Frozen):
    skill: str
    host: str
    host_version: str
    model: str
    trial_count: int
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float | None
    recall: float | None


def score_trials(path: Path) -> tuple[Score, ...]:
    corpus = decode(Corpus, (files("tum_mcp") / "bundled/activation-cases.json").read_bytes())
    cases = {case.id: case for case in corpus.root}
    trials = [
        decode(Trial, line.encode()) for line in path.read_text().splitlines() if line.strip()
    ]
    for trial in trials:
        if (
            trial.case_id not in cases
            or trial.expected_skill != cases[trial.case_id].expected_skill
        ):
            raise CampusError(Code.INVALID_RESPONSE, "Trial does not match corpus ground truth.")
        if trial.forbidden_effects:
            raise CampusError(
                Code.SCOPE_DENIED, "A forbidden effect occurred in an activation trial."
            )
    scores: list[Score] = []
    configurations = sorted({(trial.host, trial.host_version, trial.model) for trial in trials})
    for host, host_version, model in configurations:
        group = [
            trial
            for trial in trials
            if cases[trial.case_id].partition == "held_out"
            and (trial.host, trial.host_version, trial.model) == (host, host_version, model)
        ]
        for skill in sorted({case.target_skill for case in corpus.root}):
            true_positive = sum(t.expected_skill == t.selected_skill == skill for t in group)
            false_positive = sum(
                t.selected_skill == skill and t.expected_skill != skill for t in group
            )
            false_negative = sum(
                t.expected_skill == skill and t.selected_skill != skill for t in group
            )
            scores.append(
                Score(
                    skill=skill,
                    host=host,
                    host_version=host_version,
                    model=model,
                    trial_count=len(group),
                    true_positive=true_positive,
                    false_positive=false_positive,
                    false_negative=false_negative,
                    precision=true_positive / (true_positive + false_positive)
                    if true_positive + false_positive
                    else None,
                    recall=true_positive / (true_positive + false_negative)
                    if true_positive + false_negative
                    else None,
                )
            )
    return tuple(scores)
