"""Validate source requirements before reading any authored content."""

import json
from pathlib import Path

from tum_mcp.course.checks.preparation import PreparedScope, Readiness
from tum_mcp.course.ledger.coverage import read_ledger
from tum_mcp.course.ledger.preparation import (
    ExerciseDemand,
    read_preparation,
    scope_problems,
    scope_summary,
    source_byte_problems,
)
from tum_mcp.course.project.schedule import read_schedule
from tum_mcp.course.project.store import digest, load_state, read_bytes


def declaring_batches(root: Path, identifier: str) -> tuple[str, ...]:
    """The batches that list this preparation, whichever task is active."""
    from tum_mcp.course.checks.batch import Batch

    return tuple(
        path.stem
        for path in sorted((root / ".tum-mcp/batches").glob("*.json"))
        if (body := read_bytes(path)) is not None
        and identifier in Batch.model_validate_json(body).preparations
    )


def requested_scope(
    root: Path, identifier: str, batches: tuple[str, ...] | None = None
) -> dict | None:
    """The requests of the given batches, or of every batch that lists the preparation."""
    from tum_mcp.course.checks.batch import Batch

    requests = []
    for name in declaring_batches(root, identifier) if batches is None else batches:
        body = read_bytes(root / f".tum-mcp/batches/{name}.json")
        if body is not None:
            requests.append(Batch.model_validate_json(body).model_dump(mode="json"))
    return requests[0] if len(requests) == 1 else {"requests": requests} if requests else None


def assess_plan(root: Path, identifier: str, batches: tuple[str, ...] | None = None) -> Readiness:
    scope = read_preparation(root, identifier)
    if scope is None:
        return Readiness(identifier=identifier, problems=("Record the source scope first.",))
    state = load_state(root)
    schedule = read_schedule(root, state) if scope.cutoff else None
    problems = scope_problems(scope, state, read_ledger(root), schedule)
    problems.extend(source_byte_problems(root, scope, state))
    items: dict[str, list[dict]] = {}
    for demand in scope.demands:
        target = demand.target
        if target is None:
            problems.append(f"{demand.id}: name the planned teaching/practice or exercise target.")
            continue
        key = (
            f"exercises/{target.set}/{target.exercise}"
            if isinstance(demand, ExerciseDemand)
            else f"study/{target.unit}"
        )
        items.setdefault(key, []).append(demand.model_dump(mode="json"))
    request = requested_scope(root, identifier, batches)
    fingerprint = scope.fingerprint()
    if request:
        # Artifact keys are draft mappings, not the source or learner requirements.
        requests = request.get("requests", [request])
        contracts = [
            {key: value for key, value in entry.items() if key != "items"} for entry in requests
        ]
        fingerprint = digest(json.dumps([fingerprint, contracts], sort_keys=True).encode())
    return Readiness(
        identifier=identifier,
        scope=PreparedScope(identifier=identifier, fingerprint=fingerprint),
        request=request,
        mode=scope.mode,
        cutoff=scope.cutoff.isoformat() if scope.cutoff else None,
        problems=tuple(problems),
        dispositions=tuple(entry.model_dump(mode="json") for entry in scope.inventory),
        items=items,
        walkthrough_evidence=scope.walkthrough_evidence,
        **scope_summary(scope, state, problems),
    )
