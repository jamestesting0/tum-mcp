"""A fresh checker for hosts without subagents: an installed agent CLI run headless.

The checker gets read-only tools and answers on standard output, so it can read the packet
and the course but write nothing; its answers are recorded as fresh.
"""

import json
import shlex
import subprocess
from pathlib import Path

from filelock import FileLock, Timeout
from pydantic import JsonValue

from tum_mcp.course.checks.plans import plan_packet, record_gate
from tum_mcp.course.project.store import confined, private_name
from tum_mcp.course.review import loop
from tum_mcp.errors import CampusError, Code

HOSTS = {
    "claude": ["claude", "-p", "{prompt}", "--allowedTools", "Read,Grep,Glob"],
    "codex": ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check", "{prompt}"],
}
VISUAL_GUIDANCE = (
    "For requested visuals, open the item's current phone and desktop captures under "
    "`visual_sheets` before scoring. Use all six criteria with integer scores of 1, 2 or 3 "
    "when supported by the evidence. Never guess a score for a capture you could not inspect."
)
PROMPT = (
    "You are a fresh course reviewer. You did not write this content. Read the review packet "
    "at {packet} and the course files it names. For cited PDF pages, look up the source "
    "path and revision in .tum-mcp/state.json. If the revisions match, open any existing "
    ".tum-mcp/cache/pages/<sha256>/<page>.png with your image tool before trying to render "
    "the PDF again. The project is read-only. Report limits on the evidence you could inspect. "
    "Before judging, apply the packet's `guidance` for its `profile` when interpreting the "
    "shared checks. Audit source coverage using each item's preparation.demands and the "
    "packet's scope_dispositions, reading .tum-mcp/coverage.json and the source pages when "
    "needed. Do not regenerate coverage reports or browser receipts in this read-only "
    "session; the packet already contains current deterministic results. "
    "For lecture-selection, read the full compact transcript in the item's "
    "`evidence`, check every selection and omission, and inspect the comparison materials. "
    "For every item, answer every check in its "
    "`needs`, verify every finding in its `verify` and score every visual in its `visuals`, "
    "exactly in the packet's `answer` format. "
    f"{VISUAL_GUIDANCE} "
    "Rule on every `report` flag marked "
    "`needs_ruling` in `flags`. Every pass with `default_fail: true` needs its own `evidence` "
    "field. For intuition.concepts_instanced, put every planned concept name and its instance's "
    "block in that field, not only in `reason`. Resolve a finding only by quoting the rewritten "
    "passage, and only when "
    "it reads well on its own. Hunt for failures: for each check find the "
    "passage most likely to fail it. Quote word for word from the passage at its location. "
    "Reply with only the answers JSON object."
)
REPAIR_PROMPT = (
    "You are the course reviewer whose answers at {answer} for the packet at {packet} were "
    "refused: {problems} Preserve valid existing verdicts and correct supplied entries only "
    "where the error identifies a defect. Complete every omitted check, finding verification, "
    "flag ruling and visual requested by the packet, including omissions beyond the error "
    "summary. Never substitute a blanket pass or omit a required check: use uncertain with "
    "the evidence limit if it cannot be judged. Reply with only the full corrected answers "
    "JSON object. "
    f"{VISUAL_GUIDANCE}"
)
PLAN_PROMPT = (
    "You are a fresh plan checker. You did not write these plans. Read the plan packet at "
    "{packet}, the digests in .tum-mcp/digests/ and, where a digest does not settle it, the "
    "source pages they cite. Answer the packet's `ask` for every plan. Hunt for the blocking "
    "problems the `ask` names (an instance that only restates its concept is no case at all) "
    "and give other improvements as `advice`. Reply with only the answers JSON object."
)


def answers_from(output: str) -> dict:
    start, end = output.find("{"), output.rfind("}")
    if start < 0 or end <= start:
        raise CampusError(Code.INVALID_RESPONSE, "The checker replied without answers JSON.")
    try:
        value = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        raise CampusError(Code.INVALID_RESPONSE, "The checker's answers are not JSON.") from None
    if not isinstance(value, dict):
        raise CampusError(Code.INVALID_RESPONSE, "The checker's answers are not an object.")
    return value


def run(
    project: Path, packet: str | None, host: str, command: str | None = None, *, plans: bool = False
) -> dict[str, JsonValue]:
    root = project.expanduser().resolve()
    if plans:
        from tum_mcp.course.checks.batch import require_batch_plans
        from tum_mcp.course.review.items import digest

        waiting = plan_packet(root)
        if not waiting["plans"]:
            return {"recorded": [], "next": "No plan waits for the gate."}
        require_batch_plans(root, {plan["item"] for plan in waiting["plans"]})
        name = private_name(Path("."), f"review/packets/plans-{digest(waiting)}.json")
        path = confined(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(waiting, indent=2), encoding="utf-8")
        answers = _ask(root, PLAN_PROMPT.format(packet=name), host, command)
        return record_gate(root, answers.get("items", []), "fresh")
    name = private_name(Path("."), f"review/packets/{packet}.json")
    if not confined(root, name).is_file():
        raise CampusError(Code.ACTION_REQUIRED, f"No packet {packet}; run tum-mcp review next.")
    try:
        with FileLock(str(confined(root, name).with_suffix(".lock")), timeout=0):
            return _run_packet(root, name, packet, host, command)
    except Timeout:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Packet {packet} is already being checked. Wait for its existing run; "
            "use review status rather than starting another checker.",
        ) from None


def _run_packet(root: Path, name: str, packet: str, host: str, command: str | None) -> dict:
    answers = _ask(root, PROMPT.format(packet=name), host, command)
    answers["packet"] = packet
    saved = private_name(Path("."), f"review/packets/{packet}.answer.json")
    path = confined(root, saved)
    try:
        result = _record(root, answers)
    except CampusError as error:
        if error.code != Code.INVALID_RESPONSE or "Answers need fixing" not in error.message:
            raise
        # A refused answer is the checker's whole review: let it correct only what was named
        # instead of losing the round.
        path.write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
        repaired = _ask(
            root,
            REPAIR_PROMPT.format(packet=name, answer=saved, problems=error.message),
            host,
            command,
        )
        repaired["packet"] = packet
        path.write_text(json.dumps(repaired, indent=2, ensure_ascii=False), encoding="utf-8")
        return _record(root, repaired)
    path.write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _record(root: Path, answers: dict) -> dict[str, JsonValue]:
    """Record, retrying when another checker of the round wrote the records first."""
    for attempt in range(3):
        try:
            return loop.record(root, answers, "fresh")
        except CampusError as error:
            if error.code != Code.WORKSPACE_CONFLICT or attempt == 2:
                raise
    raise AssertionError("unreachable")


def _ask(root: Path, prompt: str, host: str, command: str | None) -> dict:
    template = shlex.split(command) if command else HOSTS[host]
    argv = [part.replace("{prompt}", prompt) for part in template]
    try:
        done = subprocess.run(  # noqa: S603 - argv is a fixed host CLI or the caller's template
            argv, cwd=root, capture_output=True, text=True, timeout=1800, check=False
        )
    except FileNotFoundError:
        raise CampusError(
            Code.ACTION_REQUIRED, f"{argv[0]} is not installed; use a subagent or another host."
        ) from None
    except subprocess.TimeoutExpired:
        raise CampusError(Code.ACTION_REQUIRED, "The checker ran out of time.") from None
    if done.returncode != 0:
        raise CampusError(Code.ACTION_REQUIRED, f"The checker failed with code {done.returncode}.")
    return answers_from(done.stdout)
