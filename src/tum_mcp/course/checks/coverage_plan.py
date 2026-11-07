"""Validate source requirements before reading any authored content."""

import json
from pathlib import Path

from tum_mcp.course.checks.preparation import PreparedScope, Readiness
from tum_mcp.course.ledger.coverage import read_ledger
from tum_mcp.course.ledger.preparation import ExerciseDemand, read_preparation, scope_problems
from tum_mcp.course.project.schedule import read_schedule
from tum_mcp.course.project.store import confined, digest, load_state, read_bytes


def requested_scope(root: Path, identifier: str) -> dict | None:
    from tum_mcp.course.checks.batch import Batch
    from tum_mcp.course.workflow.tasks import read_task

    task = read_task(root)
    paths = (
        [confined(root, f".tum-mcp/batches/{task.batch}.json")]
        if task
        else sorted((root / ".tum-mcp/batches").glob("*.json"))
    )
    requests = []
    for path in paths:
        body = read_bytes(path)
        batch = Batch.model_validate_json(body) if body is not None else None
        if batch and identifier in batch.preparations:
            requests.append(batch.model_dump(mode="json"))
    return requests[0] if len(requests) == 1 else {"requests": requests} if requests else None


def assess_plan(root: Path, identifier: str) -> Readiness:
    scope = read_preparation(root, identifier)
    if scope is None:
        return Readiness(identifier=identifier, problems=("Record the source scope first.",))
    state = load_state(root)
    schedule = read_schedule(root, state) if scope.cutoff else None
    problems = scope_problems(scope, state, read_ledger(root), schedule)
    resources = {entry.resource.key: entry for entry in state.resources}
    for source in scope.inventory:
        if source.disposition != "required":
            continue
        stored = resources.get(source.source)
        body = read_bytes(confined(root, stored.path)) if stored and stored.path else None
        if body is None or digest(body) != source.sha256:
            problems.append(f"{source.source}: required source bytes are missing or changed.")
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
    request = requested_scope(root, identifier)
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
    )
