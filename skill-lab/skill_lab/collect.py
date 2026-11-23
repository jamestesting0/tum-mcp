"""Workflow metrics for a finished run: delivery, study report, render check, transcript counts."""

import json
import re
import shlex
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Final

from skill_lab import LabError, hosts, paths, scenarios, variants
from skill_lab.models import ModelSpec
from skill_lab.runs import storage_environment
from tum_mcp.course.content.store import present

METRICS_DEFINITION: Final = "requested-delivery-full-report-v3"
COVERAGE_GAPS: Final = (
    "not_inspected",
    "outcome_gaps",
    "enrichment_gaps",
    "sources_without_outcomes",
    "unprepared_items",
    "units_without_outcomes",
)
SHEET_GAPS: Final = ("gaps", "sources_without_requirements", "entries_without_requirement")


def run_json(
    command: list[str], environment: dict[str, str], *, payload: str | None = None
) -> tuple[dict | None, str]:
    try:
        result = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
    except (OSError, UnicodeError) as error:
        return None, str(error)
    if result.returncode:
        return None, result.stderr.strip() or result.stdout.strip() or f"Exit {result.returncode}"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return None, f"Invalid JSON: {error}"
    if not isinstance(data, dict):
        return None, "Expected a JSON object."
    return data, ""


def study(
    python: Path, project: Path, environment: dict[str, str], *arguments: str
) -> tuple[dict | None, str]:
    return run_json(
        [str(python), "-I", "-m", "tum_mcp", "study", *arguments, str(project)], environment
    )


def report_metrics(report: dict | None, error: str) -> dict:
    metrics = {
        "report_status": "failed" if error else "not_measured",
        "report_error": error,
        "quality_flags": None,
        "coverage_gaps": None,
        "render_checked": None,
        "render_passed": None,
        "review_passed": None,
    }
    if report is None:
        return metrics
    match report:
        case {
            "quality": list() as quality,
            "coverage": dict() as coverage,
            "render": {"checked": bool() as checked, "passed": bool() as render},
            "review": {"gate": bool() as gate},
        }:
            sheet = coverage.get("cheatsheet", {})
            groups = [(coverage, COVERAGE_GAPS)]
            if "cheatsheet" in coverage:
                groups.append((sheet, SHEET_GAPS))
            if all(
                isinstance(group, dict) and all(isinstance(group.get(key), list) for key in keys)
                for group, keys in groups
            ):
                return metrics | {
                    "report_status": "measured",
                    "quality_flags": len(quality),
                    "coverage_gaps": sum(len(group[key]) for group, keys in groups for key in keys),
                    "render_checked": checked,
                    "render_passed": render,
                    "review_passed": gate,
                }
    return metrics | {"report_status": "failed", "report_error": "Missing full report fields."}


def requested_delivery(record: dict) -> dict[str, list[str]]:
    if "delivery_request" in record:
        return record["delivery_request"]
    if any("skills" in turn or "expected_items" in turn for turn in record["turns"]):
        return scenarios.delivery_request(
            [
                scenarios.Turn(
                    "", skills=turn.get("skills", []), expected_items=turn.get("expected_items", {})
                )
                for turn in record["turns"]
            ]
        )
    # Older runs only recorded messages. Use tracked/local turn metadata as long as the
    # saved prompts still match, rather than inferring demand from available workspaces.
    if name := record.get("scenario"):
        try:
            scenario = scenarios.load(name)
        except LabError:
            return {}
        turns = record["turns"]
        if turns and all(
            0 < turn["turn"] <= len(scenario.turns)
            and turn.get("message") == scenario.turns[turn["turn"] - 1].say
            for turn in turns
        ):
            return scenarios.delivery_request(scenario.turns[: max(turn["turn"] for turn in turns)])
    return {}


def measure_delivery(
    python: Path, project: Path | None, requested: dict[str, list[str]], environment: dict[str, str]
) -> dict:
    if project is None or not requested:
        return {
            name: {
                "status": "absent",
                "readable_items": [],
                "missing_items": sorted(set(keys)),
                "problems": [],
            }
            for name, keys in requested.items()
        }
    result, error = run_json(
        [str(python), "-I", str(Path(__file__).with_name("delivery.py")), str(project)],
        environment,
        payload=json.dumps(requested),
    )
    if result is not None:
        return result
    return {
        name: {
            "status": "unmeasured",
            "readable_items": [],
            "missing_items": [],
            "problems": [error],
        }
        for name in requested
    }


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
    offline = record.get("scenario") in scenarios.FAI_SCENARIOS
    environment = hosts.clean_environment(
        storage_environment(downloads, offline=offline),
        paths.profile_home(host),
        None,
        host,
        offline=offline,
    )
    delivery = measure_delivery(python, project, requested_delivery(record), environment)
    metrics: dict = {
        "run": run_id,
        "metrics_definition": METRICS_DEFINITION,
        "status": record["status"],
        "minutes": record.get("minutes"),
        "speed_tier": record.get("speed_tier")
        or ModelSpec.parse(record["author"]).tier
        or "standard",
        "questions_answered": sum(len(turn.get("replies", [])) for turn in record["turns"]),
        "project_created": project is not None,
        "delivery": delivery,
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
    report, error = None, ""
    if project is not None:
        if visuals:
            _, error = study(python, project, environment, "visuals")
            metrics["visuals_error"] = error
        report, error = study(python, project, environment, "report", "--json")
    metrics.update(report_metrics(report, error))
    if report is not None:
        (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    else:
        (run_dir / "report.json").unlink(missing_ok=True)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics
