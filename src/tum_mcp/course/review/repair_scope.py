"""Adopt complete structural additions during repair without extending review authority."""

from pathlib import Path

from tum_mcp.course.checks.batch import Batch, assess_batch
from tum_mcp.course.content.exam_data import read_exam
from tum_mcp.course.ledger.preparation import read_preparation
from tum_mcp.course.project.store import Write, apply, load_state, private_path, read_bytes
from tum_mcp.course.review.items import digest
from tum_mcp.errors import CampusError, Code


def contract(root: Path, identifier: str, sources: tuple[str, ...] | None = None) -> str:
    batch = Batch.model_validate_json(private_path(root, f"batches/{identifier}.json").read_bytes())
    exam = read_exam(root)
    return digest(
        {
            "request": batch.model_dump(mode="json", exclude={"items"}),
            "preparations": {
                key: scope.fingerprint() if (scope := read_preparation(root, key)) else None
                for key in batch.preparations
            },
            "sources": sorted(
                (entry.resource.key, entry.sha256)
                for entry in load_state(root).resources
                if sources is None or entry.resource.key in sources
            ),
            "past_questions": sorted(
                (
                    question.key,
                    question.number,
                    question.locator,
                    tuple(source.key for source in variant.sources),
                )
                for _, variant, question in exam.past_questions().values()
            )
            if exam
            else [],
        }
    )


def repair_scope(root: Path, reason: str) -> dict:
    from tum_mcp.course.review import loop

    context = loop.load(root)
    state = loop.read_state(context.root)
    if not reason.strip():
        raise CampusError(Code.ACTION_REQUIRED, "Explain the structural repair with --reason.")
    if state is None or state.batch is None or not state.rounds:
        raise CampusError(Code.ACTION_REQUIRED, "Repair scope after a batch review round starts.")
    if state.rounds[-1].pending_packets:
        raise CampusError(
            Code.ACTION_REQUIRED, "Record all review packets before structural repair."
        )
    if state.batch_contract != contract(context.root, state.batch.identifier, state.batch_sources):
        raise CampusError(
            Code.ACTION_REQUIRED,
            "The original request or source requirements changed; use a new task.",
        )
    reading = assess_batch(context.root, state.batch.identifier, context)
    loop._require_ready(reading)
    before, after = set(state.scope), set(reading.items)
    if not before <= after:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Keep original item keys when splitting; no reviewed item may disappear.",
        )
    added = sorted(after - before)
    if not added or any(
        key.split("/")[0] not in {k.split("/")[0] for k in before} for key in added
    ):
        raise CampusError(
            Code.ACTION_REQUIRED, "Add complete repair items within the reviewed workspaces."
        )
    updated = state.model_copy(
        update={
            "scope": tuple(reading.items),
            "batch": reading.scope,
            "status": ("budget_spent" if state.round >= state.budget else "running")
            if state.rounds[-1].closed
            else state.status,
            "structural_repairs": (
                *state.structural_repairs,
                {
                    "round": state.round,
                    "added": added,
                    "reason": reason,
                },
            ),
        }
    )
    loop._bind_preparation(context, updated)
    card = loop.scorecard(context, updated)
    name = ".tum-mcp/loop/scorecard.md"
    apply(
        context.root,
        (
            loop._state_write(context.root, updated),
            Write(
                name,
                read_bytes(private_path(context.root, "loop/scorecard.md")),
                loop._markdown(card).encode(),
            ),
        ),
    )
    return {
        "added": added,
        "round": updated.round,
        "budget": updated.budget,
        "next": (
            "Report the repaired round. "
            if state.rounds[-1].closed
            else "Close the repaired round. "
        )
        + "Added items have no new review or transferred scores; "
        "report remaining verification. Another round requires user authorization.",
    }
