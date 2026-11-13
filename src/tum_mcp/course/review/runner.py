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
    "For requested visuals, open the item's current desktop captures (phone only when asked) under "
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
    f"{loop.REPAIR_GUIDANCE} "
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
    "it reads well on its own. Hunt for failures: for each check inspect the passages most "
    "likely to fail it. File each defect once under the owner check from the rubric's "
    "'One owner per problem' table; list other asked checks it fails in the finding's `also`. "
    "Pass when those passages pass. If the subject is absent, pass and say "
    "so. Uncertain requires a non-empty missing field naming the specific artifact or source "
    "page that cannot be opened and why. Incomplete sampling or 'not independently verified' "
    "is not unavailable evidence: a sampled check whose likeliest failures pass is a pass. For "
    "correctness.recomputed and correctness.answer_key, inspect the key script's inputs against "
    "the sources and spot-check: a passing key proves agreement, not correctness. "
    "Quote word for word from the passage at its location. "
    "Reply with only the answers JSON object."
)
REPAIR_PROMPT = (
    "You are the course reviewer whose answers at {answer} for the packet at {packet} were "
    "refused: {problems} Reply with only a partial answers JSON object containing the refused "
    "entries. To replace a finding, include `_index` with its zero-based index from the "
    "problem; omit it to append a new finding. Never substitute a blanket pass: use "
    "uncertain only with a missing field naming the specific artifact or source page that "
    "cannot be opened and why. 'Not independently verified' or 'did not inspect every' is "
    "not unavailable evidence: a sampled check whose likeliest failures pass is a pass. "
    "Answer only the listed missing or invalid entries; preserve all other answers. "
    f"{VISUAL_GUIDANCE}"
)
PLAN_PROMPT = (
    "You are a fresh plan checker. You did not write these plans. Read the plan packet at "
    "{packet}, the digests in .tum-mcp/digests/ and, where a digest does not settle it, the "
    "source pages they cite. Answer the packet's `ask` for every plan. On the first check, "
    "find every blocker in one pass. On later checks, verify every earlier reason first; "
    "raise a new blocker only for a change or a break caused by it. An instance that only "
    "restates its concept is no case at all. Give other improvements as `advice`. "
    "Reply with only the answers JSON object."
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
    for attempt in range(3):
        path.write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            return _record(root, answers, partial=attempt == 2)
        except loop.AnswerError as error:
            if attempt == 2:
                raise
            repaired = _ask(
                root,
                REPAIR_PROMPT.format(
                    packet=name, answer=saved, problems=json.dumps(error.problems)
                ),
                host,
                command,
            )
            answers = merge_answers(answers, repaired)
    raise AssertionError("unreachable")


def merge_answers(original: dict, repair: dict) -> dict:
    merged = json.loads(json.dumps(original))
    items = {item["item"]: item for item in merged.get("items", [])}
    for correction in repair.get("items", []):
        key = correction["item"]
        if key not in items:
            merged.setdefault("items", []).append(correction)
            items[key] = correction
            continue
        item = items[key]
        item.setdefault("checks", {}).update(correction.get("checks", {}))
        for field, identity in (("verify", "finding"), ("flags", "key"), ("visuals", "visual")):
            entries = item.setdefault(field, [])
            for changed in correction.get(field, []):
                existing = next(
                    (i for i, entry in enumerate(entries) if entry[identity] == changed[identity]),
                    None,
                )
                if existing is None:
                    entries.append(changed)
                else:
                    entries[existing] = changed
        findings = item.setdefault("findings", [])
        for changed in correction.get("findings", []):
            changed = dict(changed)
            index = changed.pop("_index", None)
            if index is None:
                findings.append(changed)
            elif isinstance(index, int) and 0 <= index < len(findings):
                findings[index] = changed
            else:
                raise CampusError(Code.INVALID_RESPONSE, "The repaired finding index is invalid.")
    return merged


def _record(root: Path, answers: dict, *, partial: bool = False) -> dict[str, JsonValue]:
    """Record, retrying when another checker of the round wrote the records first."""
    for attempt in range(3):
        try:
            return loop.record(root, answers, "fresh", partial=partial)
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
