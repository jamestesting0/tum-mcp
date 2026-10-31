"""Workflow metrics for a finished run: delivery, study report, render check, transcript counts."""

import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from skill_lab import paths, variants
from skill_lab.runs import storage_environment


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
    for path in sorted((run_dir / "transcript").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if host == "claude":
                message = event.get("message") if isinstance(event.get("message"), dict) else {}
                for block in message.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        tools[str(block.get("name"))] += 1
                    elif block.get("type") == "tool_result" and block.get("is_error"):
                        errors += 1
                if event.get("type") == "result":
                    usage = event.get("usage") or {}
                    tokens += int(usage.get("input_tokens") or 0)
                    tokens += int(usage.get("output_tokens") or 0)
            else:
                item = event.get("item") or {}
                if event.get("type") == "item.completed" and item.get("type") in {
                    "command_execution",
                    "mcp_tool_call",
                }:
                    name = item.get("tool") or item.get("type")
                    tools[str(name)] += 1
                    if item.get("status") == "failed" or item.get("exit_code") not in (None, 0):
                        errors += 1
                if event.get("type") == "turn.completed":
                    usage = event.get("usage") or {}
                    tokens += int(usage.get("input_tokens") or 0)
                    tokens += int(usage.get("output_tokens") or 0)
    campus = sum(n for name, n in tools.items() if "tum" in name or "moodle" in name)
    return {
        "tool_calls": sum(tools.values()),
        "campus_calls": campus,
        "tool_errors": errors,
        "tokens": tokens,
        "top_tools": dict(tools.most_common(12)),
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
        "questions_answered": sum(len(turn.get("replies", [])) for turn in record["turns"]),
        "project_created": project is not None,
        "delivered": bool(
            project
            and any(
                (project / "app" / name).is_file() for name in ("content.json", "exercises.json")
            )
        ),
        "lessons_built": bool(project and (project / "app" / "content.json").is_file()),
        "exercises_built": bool(project and (project / "app" / "exercises.json").is_file()),
        **transcript_stats(run_dir, host),
        "files_outside_project": files_outside_project(run_dir, record.get("project")),
    }
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
