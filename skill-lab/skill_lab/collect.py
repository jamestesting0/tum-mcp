"""Workflow metrics for a finished run: delivery, study report, render check, transcript counts."""

import json
import os
import re
import shlex
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

from skill_lab import paths, variants
from skill_lab.models import ModelSpec
from skill_lab.runs import storage_environment
from tum_mcp.course.content.store import present


def count_items(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return sum(count_items(item) for item in value.values() if isinstance(item, list | dict))
    return 0


def study(python: Path, project: Path, downloads: Path, *arguments: str) -> tuple[dict, str]:
    environment = {**os.environ, **storage_environment(downloads)}
    result = subprocess.run(
        [str(python), "-I", "-m", "tum_mcp", "study", *arguments, str(project)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    if result.returncode:
        return {}, result.stderr.strip()[-600:]
    try:
        return json.loads(result.stdout), ""
    except ValueError:
        return {}, ""


def transcript_stats(run_dir: Path, host: str) -> dict:
    tools: Counter[str] = Counter()
    errors = 0
    tokens = 0
    output_chars = 0
    output_bytes = 0
    phases = []
    # Codex reports a thread's usage cumulatively at every turn.completed, so a turn's own
    # tokens are the difference from the thread's previous report.
    thread, seen = "", {}
    turn_tokens: list[int] = []
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    for turn in sorted(record["turns"], key=lambda entry: entry["turn"]):
        for part in turn["parts"]:
            path = run_dir / "transcript" / f"{part['label']}.jsonl"
            started = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                stamp = event.get("_lab_timestamp") or event.get("timestamp")
                if host == "claude":
                    message = event.get("message") if isinstance(event.get("message"), dict) else {}
                    for block in message.get("content") or []:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tools[str(block.get("name"))] += 1
                            started[block["id"]] = (stamp, block)
                        elif block.get("type") == "tool_result":
                            start, call = started.pop(block.get("tool_use_id"), (None, {}))
                            content = block.get("content")
                            if isinstance(content, str | list):
                                text = (
                                    content
                                    if isinstance(content, str)
                                    else json.dumps(content, ensure_ascii=False)
                                )
                                output_chars += len(text)
                                output_bytes += len(text.encode("utf-8"))
                            phases.append(
                                {
                                    "turn": turn["turn"],
                                    "part": part["label"],
                                    "kind": command_kind(
                                        (call.get("input") or {}).get("command", "")
                                    )
                                    if call.get("name") == "Bash"
                                    else str(call.get("name") or "tool"),
                                    **phase_times(start, stamp),
                                }
                            )
                            if block.get("is_error"):
                                errors += 1
                    if event.get("type") == "result":
                        usage = event.get("usage") or {}
                        tokens += int(usage.get("input_tokens") or 0)
                        tokens += int(usage.get("output_tokens") or 0)
                else:
                    item = event.get("item") or {}
                    if event.get("type") == "item.started":
                        started[item.get("id")] = stamp
                    if event.get("type") == "thread.started":
                        thread = str(event.get("thread_id") or "")
                    if event.get("type") == "item.completed" and item.get("type") in {
                        "command_execution",
                        "mcp_tool_call",
                    }:
                        name = item.get("tool") or item.get("type")
                        tools[str(name)] += 1
                        output = item.get("aggregated_output") or item.get("result") or ""
                        text = (
                            output
                            if isinstance(output, str)
                            else json.dumps(output, ensure_ascii=False)
                        )
                        output_chars += len(text)
                        output_bytes += len(text.encode("utf-8"))
                        phases.append(
                            {
                                "turn": turn["turn"],
                                "part": part["label"],
                                "kind": command_kind(item.get("command", ""))
                                if item["type"] == "command_execution"
                                else str(name),
                                "status": item.get("status", "completed"),
                                **phase_times(started.pop(item.get("id"), None), stamp),
                            }
                        )
                        if item.get("status") == "failed" or item.get("exit_code") not in (None, 0):
                            errors += 1
                    if event.get("type") == "turn.completed":
                        usage = event.get("usage") or {}
                        total = int(usage.get("input_tokens") or 0) + int(
                            usage.get("output_tokens") or 0
                        )
                        turn_tokens.append(total - seen.get(thread, 0))
                        seen[thread] = total
    if host != "claude":
        tokens = sum(seen.values())
    campus = sum(n for name, n in tools.items() if "tum" in name or "moodle" in name)
    return {
        "tool_calls": sum(tools.values()),
        "campus_calls": campus,
        "tool_errors": errors,
        "tokens": tokens,
        **({"turn_tokens": turn_tokens} if turn_tokens else {}),
        "output_chars": output_chars,
        "output_bytes": output_bytes,
        **(
            {"phase_table": sorted(phases, key=lambda row: (row["turn"], row.get("start", "")))}
            if phases
            else {}
        ),
        "top_tools": dict(tools.most_common(12)),
    }


def command_kind(command: str) -> str:
    """Group CLI operations without storing command arguments or prompt contents."""
    if match := re.search(r"\btum-mcp['\"]?\s+([\w-]+)\s+([\w-]+)", command):
        group, action = match.groups()
        if (group, action) == ("review", "run-checker"):
            return "plan_check" if "--plans" in command else "review_packet"
        return f"{group}.{action}"
    try:
        parts = shlex.split(command)
        if len(parts) >= 3 and parts[1] in {"-lc", "-c"}:
            parts = shlex.split(parts[2])
    except ValueError:
        return "shell"
    return Path(parts[0]).name if parts else "command"


def phase_times(start: str | None, end: str | None) -> dict:
    """Old transcripts have no clock; never turn missing timestamps into zero time."""
    times = {key: value for key, value in (("start", start), ("end", end)) if value}
    if start and end:
        times["minutes"] = round(
            (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60, 4
        )
    return times


def checker_phases(workspace: Path, phases: list[dict]) -> list[dict]:
    """Place every broker checker invocation, including repairs, in its author's turn."""
    sessions = []
    for path in (workspace / ".lab-broker").glob("*.sessions.jsonl"):
        attempts = {}
        completed = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            attempt = event["attempt"]
            if event["event"] == "started":
                attempts[attempt] = event
            elif event["event"] == "completed":
                start = attempts[attempt]
                parent = next(
                    (
                        phase
                        for phase in phases
                        if phase.get("start")
                        and phase.get("end")
                        and datetime.fromisoformat(phase["start"])
                        <= datetime.fromisoformat(start["timestamp"])
                        and datetime.fromisoformat(phase["end"])
                        >= datetime.fromisoformat(event["timestamp"])
                    ),
                    None,
                )
                completed[attempt] = {
                    **({"turn": parent["turn"], "part": parent["part"]} if parent else {}),
                    "kind": start["kind"],
                    "attempt": attempt,
                    "repair": attempt > 0,
                    "status": event["status"],
                    **phase_times(start["timestamp"], event["timestamp"]),
                }
        response_path = path.with_name(path.name.replace(".sessions.jsonl", ".response.json"))
        response = (
            json.loads(response_path.read_text(encoding="utf-8")) if response_path.is_file() else {}
        )
        # A later invocation is direct evidence that the preceding answer was refused.
        for attempt, start in attempts.items():
            session = completed.get(attempt) or {
                "kind": start["kind"],
                "attempt": attempt,
                "repair": attempt > 0,
                "start": start["timestamp"],
            }
            if attempt < max(attempts):
                session["status"] = "refused"
            elif "Answers need fixing" in response.get("stderr", ""):
                session["status"] = "refused"
            sessions.append(session)
    return sorted(sessions, key=lambda phase: phase["start"])


def review_stats(workspace: Path) -> dict:
    """Checker sessions the lab broker ran, and the review verdicts they recorded."""
    plans = packets = 0
    for path in (workspace / ".lab-broker").glob("*.response.json"):
        try:
            stdout = json.loads(path.read_text(encoding="utf-8")).get("stdout") or ""
            answer = json.loads(stdout)
        except ValueError:
            continue
        if "verdicts" in answer:
            plans += 1
        elif "opened" in answer:
            packets += 1
    verdicts: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    for path in workspace.glob("**/.tum-mcp/review/packets/*.answer.json"):
        for item in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
            for check in (item.get("checks") or {}).values():
                verdicts[str(check.get("verdict"))] += 1
                if check.get("verdict") == "uncertain":
                    cause = check.get("missing") or check.get("reason")
                    if cause:
                        causes[str(cause)] += 1
    return {
        "plan_checks": plans,
        "packet_checks": packets,
        "verdicts": dict(verdicts),
        **({"uncertain_causes": dict(causes)} if causes else {}),
    }


def files_outside_project(run_dir: Path, project: str | None) -> list[str]:
    history = run_dir / "history.git"
    listed = subprocess.run(
        ["git", f"--git-dir={history}", "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    if not project:
        return listed[:50]
    prefix = project.rstrip("/") + "/"
    return [path for path in listed if project != "." and not path.startswith(prefix)][:50]


def collect_run(round_id: str, run_id: str, *, visuals: bool = True) -> dict:
    run_dir = paths.round_dir(round_id) / "runs" / run_id
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    host = record["author"].split(":", 1)[0]
    workspace, downloads = run_dir / "workspace", run_dir / "downloads"
    project = workspace / record["project"] if record.get("project") else None
    python = variants.python_of(paths.round_dir(round_id) / "variants" / record["variant"])
    metrics: dict = {
        "run": run_id,
        "status": record["status"],
        "minutes": record.get("minutes"),
        "speed_tier": record.get("speed_tier")
        or ModelSpec.parse(record["author"]).tier
        or "standard",
        "questions_answered": sum(len(turn.get("replies", [])) for turn in record["turns"]),
        "project_created": project is not None,
        "delivered": bool(
            project and any(present(project, workspace) for workspace in ("study", "exercises"))
        ),
        "lessons_built": bool(project and present(project, "study")),
        "exercises_built": bool(project and present(project, "exercises")),
        **transcript_stats(run_dir, host),
        **review_stats(workspace),
        "files_outside_project": files_outside_project(run_dir, record.get("project")),
    }
    sessions = checker_phases(workspace, metrics.get("phase_table", []))
    if sessions:
        metrics["checker_sessions"] = sessions
        metrics["phase_table"] = sorted(
            [*metrics.get("phase_table", []), *sessions],
            key=lambda row: (row.get("turn", 0), row.get("start", "")),
        )
    for phase in metrics.get("phase_table", []):
        phase["source"] = "checker" if "attempt" in phase else "command"
    if project is not None:
        if visuals:
            _, error = study(python, project, downloads, "visuals")
            metrics["visuals_error"] = error
        report, error = study(python, project, downloads, "report")
        metrics["report_error"] = error
        metrics["quality_flags"] = count_items(report.get("quality"))
        metrics["coverage_gaps"] = count_items(report.get("coverage"))
        metrics["render_passed"] = (report.get("render") or {}).get("passed")
        metrics["review_passed"] = (report.get("review") or {}).get("passed")
        (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics
