"""Headless Claude Code and Codex turns: command lines, output parsing, reported models."""

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from skill_lab.models import ModelSpec

CLAUDE_ALLOWED = (
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "Glob",
    "Grep",
    "TodoWrite",
    "Skill",
    "Task",
    "Bash",
    "mcp__tum",
)
CLAUDE_DISALLOWED = (
    "WebFetch",
    "WebSearch",
    "Bash(git push:*)",
    "Bash(gh:*)",
    "Bash(curl:*)",
    "Bash(wget:*)",
    "Bash(npm publish:*)",
)
JUDGE_ALLOWED = ("Read", "Glob", "Grep")
DROPPED_ENV_PREFIXES = ("CLAUDE_CODE_", "CODEX_", "OMO_", "SENPI_", "PI_", "UV_")
DROPPED_ENV = frozenset(
    {"CLAUDECODE", "CLAUDE_CONFIG_DIR", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"}
)


@dataclass
class TurnResult:
    session_id: str | None = None
    text: str = ""
    model_reported: str | None = None
    usage: dict = field(default_factory=dict)
    cost_usd: float | None = None
    is_error: bool = False
    error: str = ""
    events: list[dict] = field(default_factory=list)


def clean_environment(
    extra: dict[str, str], profile: Path, path_prefix: Path | None, host: str
) -> dict:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in DROPPED_ENV and not key.startswith(DROPPED_ENV_PREFIXES)
    }
    browsers = Path.home() / "Library" / "Caches" / "ms-playwright"
    if browsers.is_dir():
        environment.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    environment.update(extra)
    if host == "claude":
        environment["CLAUDE_CONFIG_DIR"] = str(profile)
    else:
        environment["HOME"] = str(profile)
    if path_prefix is not None:
        environment["PATH"] = f"{path_prefix}{os.pathsep}{environment.get('PATH', '')}"
    return environment


def claude_command(
    spec: ModelSpec,
    message: str,
    *,
    session: str | None,
    judge: bool = False,
) -> list[str]:
    command = [
        "claude",
        "-p",
        message,
        "--model",
        spec.model,
        "--effort",
        spec.effort,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if judge:
        command += ["--strict-mcp-config", "--allowedTools", ",".join(JUDGE_ALLOWED)]
        command += ["--disallowedTools", "Bash,Write,Edit,WebFetch,WebSearch"]
    else:
        command += ["--permission-mode", "acceptEdits"]
        command += ["--allowedTools", ",".join(CLAUDE_ALLOWED)]
        command += ["--disallowedTools", ",".join(CLAUDE_DISALLOWED)]
    if session:
        command += ["--resume", session]
    return command


def codex_command(
    spec: ModelSpec,
    message: str,
    workspace: Path,
    *,
    session: str | None,
    judge: bool = False,
) -> list[str]:
    command = [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-C",
        str(workspace),
        "-m",
        spec.model,
        "-c",
        f'model_reasoning_effort="{spec.effort}"',
    ]
    if judge:
        command += ["-s", "read-only", "-c", "mcp_servers={}"]
    else:
        command += ["-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=false"]
    if session:
        command += ["resume", session]
    command.append(message)
    return command


def parse_lines(output: str) -> list[dict]:
    events = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def parse_claude(events: list[dict]) -> TurnResult:
    result = TurnResult(events=events)
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            result.session_id = event.get("session_id") or result.session_id
            result.model_reported = event.get("model") or result.model_reported
        elif event.get("type") == "assistant":
            model = (event.get("message") or {}).get("model")
            if model and model != "<synthetic>":
                result.model_reported = model
        elif event.get("type") == "result":
            result.session_id = event.get("session_id") or result.session_id
            result.text = str(event.get("result") or "")
            result.usage = event.get("usage") or {}
            result.cost_usd = event.get("total_cost_usd")
            result.is_error = bool(event.get("is_error")) or event.get("subtype") != "success"
            if result.is_error:
                result.error = str(event.get("result") or event.get("subtype"))[:500]
    if not any(event.get("type") == "result" for event in events):
        result.is_error = True
        result.error = result.error or "Claude ended without a result event."
    return result


def codex_session_model(home: Path, thread_id: str | None) -> str | None:
    if not thread_id:
        return None
    for path in sorted((home / ".codex" / "sessions").rglob(f"*{thread_id}*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if '"turn_context"' not in line:
                continue
            try:
                payload = json.loads(line).get("payload") or {}
            except ValueError:
                continue
            if payload.get("model"):
                return str(payload["model"])
    return None


def parse_codex(events: list[dict], home: Path) -> TurnResult:
    result = TurnResult(events=events)
    messages = []
    for event in events:
        kind = event.get("type")
        if kind == "thread.started":
            result.session_id = event.get("thread_id")
        elif kind == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                messages.append(str(item["text"]))
        elif kind == "turn.completed":
            result.usage = event.get("usage") or {}
        elif kind in {"turn.failed", "error"}:
            result.is_error = True
            error = event.get("error") or event.get("message") or kind
            result.error = str(error)[:500]
    result.text = messages[-1] if messages else ""
    if not any(event.get("type") == "turn.completed" for event in events):
        result.is_error = True
        result.error = result.error or "Codex ended without completing the turn."
    result.model_reported = codex_session_model(home, result.session_id)
    return result


def run_turn(
    spec: ModelSpec,
    message: str,
    *,
    workspace: Path,
    environment: dict,
    session: str | None,
    timeout: int,
    raw: Path,
    judge: bool = False,
) -> TurnResult:
    if spec.host == "claude":
        command = claude_command(spec, message, session=session, judge=judge)
    else:
        command = codex_command(spec, message, workspace, session=session, judge=judge)
    raw.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output, failure = completed.stdout, ""
        if completed.returncode and not output.strip():
            failure = f"exit {completed.returncode}: {completed.stderr.strip()[-400:]}"
    except subprocess.TimeoutExpired as expired:
        output = expired.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        failure = f"turn timed out after {timeout}s"
    raw.write_text(output, encoding="utf-8")
    events = parse_lines(output)
    if spec.host == "claude":
        result = parse_claude(events)
    else:
        result = parse_codex(events, Path(environment["HOME"]))
    if failure:
        result.is_error = True
        result.error = failure
    return result
