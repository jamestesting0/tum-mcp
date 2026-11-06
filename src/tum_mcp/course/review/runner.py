"""A fresh checker for hosts without subagents: an installed agent CLI run headless.

The checker gets read-only tools and answers on standard output, so it can read the packet
and the course but write nothing; its answers are recorded as fresh.
"""

import json
import shlex
import subprocess
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.course.checks.plans import plan_packet, record_gate
from tum_mcp.course.project.store import confined, private_name
from tum_mcp.course.review import loop
from tum_mcp.errors import CampusError, Code

HOSTS = {
    "claude": ["claude", "-p", "{prompt}", "--allowedTools", "Read,Grep,Glob"],
    "codex": ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check", "{prompt}"],
}
PROMPT = (
    "You are a fresh course reviewer. You did not write this content. Read the review packet "
    "at {packet} and the course files it names. For cited PDF pages, look up the source "
    "path and revision in .tum-mcp/state.json. If the revisions match, open any existing "
    ".tum-mcp/cache/pages/<sha256>/<page>.png with your image tool before trying to render "
    "the PDF again. The project is read-only. Report limits on the evidence you could inspect. "
    "Before judging, apply the packet's `guidance` for its `profile` when interpreting the "
    "shared checks. For every item, answer every check in its "
    "`needs`, verify every finding in its `verify` and score every visual in its `visuals`, "
    "exactly in the packet's `answer` format. Rule on every `report` flag marked "
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
    "refused: {problems} Correct only what is named, keep every other verdict, and reply with "
    "only the full corrected answers JSON object."
)
PLAN_PROMPT = (
    "You are a fresh plan checker. You did not write these plans. Read the plan packet at "
    "{packet}, the digests in .tum-mcp/digests/ and, where a digest does not settle it, the "
    "source pages they cite. Answer the packet's `ask` for every plan. Hunt for weak plans: an "
    "instance that restates its concept is not a worked instance. Reply with only the answers "
    "JSON object."
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
        waiting = plan_packet(root)
        if not waiting["plans"]:
            return {"recorded": [], "next": "No plan waits for the gate."}
        name = private_name(Path("."), "review/packets/plans.json")
        path = confined(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(waiting, indent=2), encoding="utf-8")
        answers = _ask(root, PLAN_PROMPT.format(packet=name), host, command)
        return record_gate(root, answers.get("items", []), "fresh")
    name = private_name(Path("."), f"review/packets/{packet}.json")
    if not confined(root, name).is_file():
        raise CampusError(Code.ACTION_REQUIRED, f"No packet {packet}; run tum-mcp review next.")
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
