"""`tum-mcp review`: the review loop for every workspace, driven by the review-course skill."""

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from tum_mcp.course.review import loop, registry
from tum_mcp.errors import CampusError, Code

app = typer.Typer(no_args_is_help=True)


def _echo(value: object) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


@app.command()
def start(
    project: Path,
    rounds: Annotated[int, typer.Option(min=1, max=20, help="Round budget.")] = loop.DEFAULT_ROUNDS,
    workspace: Annotated[
        list[str] | None,
        typer.Option(help="Only study, exercises, exam, lectures or course; repeatable."),
    ] = None,
    preparation: Annotated[
        str | None, typer.Option(help="Review a ready preparation scope ID.")
    ] = None,
    batch: Annotated[
        str | None, typer.Option(help="Review one complete multi-workspace batch.")
    ] = None,
    ad_hoc: Annotated[
        bool, typer.Option(help="Explicitly review part of a declared batch.")
    ] = False,
) -> None:
    """Fix the scope and the round budget for a new review loop."""
    state = loop.start(
        project,
        rounds,
        tuple(workspace or ()),
        preparation=preparation,
        batch=batch,
        ad_hoc=ad_hoc,
    )
    _echo({"items": len(state.scope), "budget": state.budget, "next": "tum-mcp review next"})


@app.command(name="next")
def next_command(project: Path) -> None:
    """Open the next round and write its checker packets."""
    _echo(loop.next_round(project))


@app.command()
def record(
    project: Path,
    file: Annotated[Path, typer.Option(help="A checker's answers for one packet, as JSON.")],
    provenance: Annotated[
        Literal["fresh", "same", "provisional"],
        typer.Option(help="fresh: a checker that did not write the content."),
    ] = "same",
) -> None:
    """Validate and save a checker's answers."""
    try:
        answers = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise CampusError(Code.INVALID_RESPONSE, "The answers file is not readable JSON.") from None
    _echo(loop.record(project, answers, provenance))


@app.command()
def fix(
    project: Path,
    item: Annotated[str, typer.Option(help="Item key.")],
    finding: Annotated[str, typer.Option(help="Finding id, such as F3.")],
    block: Annotated[
        str | None, typer.Option(help="The block you changed, when not the quoted one.")
    ] = None,
) -> None:
    """Mark a finding fixed; refused while its passage is unchanged."""
    _echo(loop.change(project, item, finding, "fixed", block=block).model_dump(mode="json"))


@app.command()
def reject(
    project: Path,
    item: Annotated[str, typer.Option()],
    finding: Annotated[str, typer.Option()],
    reason: Annotated[str, typer.Option(help="Why the content is right as written.")],
) -> None:
    """Reject a finding with the reason the content is right; checkers see it next round."""
    _echo(loop.change(project, item, finding, "rejected", reason=reason).model_dump(mode="json"))


@app.command()
def keep(
    project: Path,
    item: Annotated[str, typer.Option()],
    finding: Annotated[str, typer.Option()],
    reason: Annotated[str, typer.Option(help="Why the content cannot fix it.")],
) -> None:
    """Keep a score-2 finding the content cannot fix, with the reason."""
    _echo(loop.change(project, item, finding, "kept", reason=reason).model_dump(mode="json"))


@app.command()
def resolve(
    project: Path,
    item: Annotated[str, typer.Option()],
    check: Annotated[str, typer.Option()],
    verdict: Annotated[Literal["pass", "fail"], typer.Option()],
    reason: Annotated[str, typer.Option()],
) -> None:
    """Record the user's decision on an uncertain check."""
    loop.resolve(project, item, check, verdict, reason)
    _echo({"item": item, "check": check, "verdict": verdict})


@app.command(name="close-round")
def close_round(
    project: Path,
    incomplete: Annotated[bool, typer.Option(help="Close even with unanswered packets.")] = False,
) -> None:
    """Compute the gate, save the scorecard and end the round."""
    _echo(loop.close_round(project, incomplete=incomplete))


@app.command(name="repair-scope")
def repair_scope(project: Path, reason: Annotated[str, typer.Option()]) -> None:
    """Include complete split-out repair items without another review round or carried scores."""
    from tum_mcp.course.review.repair_scope import repair_scope as adopt

    _echo(adopt(project, reason))


@app.command()
def extend(project: Path, rounds: Annotated[int, typer.Option(min=1, max=10)] = 1) -> None:
    """Add rounds after the user agrees to go on."""
    _echo(loop.extend(project, rounds).model_dump(mode="json"))


@app.command()
def status(project: Path) -> None:
    """Where the loop stands and the one next action."""
    _echo(loop.status(project))


@app.command()
def scorecard(project: Path) -> None:
    """The current scorecard."""
    context = loop.load(project)
    state = loop.read_state(context.root)
    if state is None:
        raise CampusError(Code.ACTION_REQUIRED, "No review loop yet: tum-mcp review start.")
    _echo(loop.scorecard(context, state))


@app.command()
def checklist(
    profile: Annotated[
        Literal[
            "study-unit",
            "exercise",
            "exam-pattern",
            "exam-sheet",
            "exam-mock-question",
            "lecture-entry",
            "course",
        ],
        typer.Option(help="The kind of item you are writing or checking."),
    ],
) -> None:
    """The checks for one kind of item, each with a pass and a fail example."""
    from importlib.resources import files

    exemplars = files("tum_mcp") / "bundled/exemplars"
    # A gate-passing item of this kind to copy the shape from: read it before writing.
    shown = {
        "study-unit": {
            "content": str(exemplars / "study.json"),
            "plan": str(exemplars / "plans/study/bfs.json"),
            "answer_key": str(exemplars / "checks/study/bfs.py"),
        },
        "exercise": {"content": str(exemplars / "exercises.json")},
        "exam-pattern": {"content": str(exemplars / "exam-pattern.json")},
        "lecture-entry": {"content": str(exemplars / "lecture-note.json")},
    }
    _echo(
        {
            "profile": profile,
            **({"exemplar": shown[profile]} if profile in shown else {}),
            "checks": [check.brief() for check in registry.judged(profile)],
            "decided_by_code": [
                {"check": check.id, "flag": check.decided_by}
                for check in registry.for_profile(profile)
                if check.decided_by
            ],
        }
    )


@app.command()
def plans(
    project: Path,
    item: Annotated[
        list[str] | None, typer.Option(help="Exact plan item to read. Repeat for a batch.")
    ] = None,
) -> None:
    """Read a batch of plans or all plans awaiting a fresh checker."""
    from tum_mcp.course.checks.plans import plan_packet

    _echo(plan_packet(project.expanduser().resolve(), tuple(item or ())))


@app.command(name="plan-record")
def plan_record(
    project: Path,
    file: Annotated[Path, typer.Option(help="The checker's answer: {items: [...]}.")],
    provenance: Annotated[
        Literal["fresh", "same"],
        typer.Option(help="fresh: a checker that did not write the plans; same stays provisional."),
    ] = "same",
) -> None:
    """Record the plan gate's verdicts against each plan as it was read."""
    from tum_mcp.course.checks.plans import record_gate

    answers = json.loads(file.read_bytes()).get("items", [])
    _echo(record_gate(project.expanduser().resolve(), answers, provenance))


@app.command(name="run-checker")
def run_checker(
    project: Path,
    packet: Annotated[str | None, typer.Option(help="Packet id from review next.")] = None,
    plans: Annotated[
        bool, typer.Option("--plans", help="Check the plans waiting for the gate.")
    ] = False,
    host: Annotated[Literal["claude", "codex"], typer.Option()] = "claude",
    command: Annotated[
        str | None, typer.Option(help="A checker command template; {prompt} is replaced.")
    ] = None,
) -> None:
    """Check a packet, or the waiting plans, in a separate headless session, recorded fresh."""
    from tum_mcp.course.review.runner import run

    if plans == (packet is not None):
        raise CampusError(Code.ACTION_REQUIRED, "Name one packet with --packet, or use --plans.")
    _echo(run(project, packet, host, command, plans=plans))
