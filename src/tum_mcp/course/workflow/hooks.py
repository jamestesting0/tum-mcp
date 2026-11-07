"""Native lifecycle contracts around the shared course completion decision."""

import shlex
from typing import Literal

from tum_mcp.course.workflow import tasks

Host = Literal["codex", "claude", "cursor", "antigravity"]


def handle(host: Host, payload: dict, event: str | None = None) -> dict:
    event = event or payload.get("hook_event_name", "Stop")
    identity = payload.get(
        "conversationId"
        if host == "antigravity"
        else "conversation_id"
        if host == "cursor"
        else "session_id"
    )
    if host == "cursor" and not identity:
        identity = payload.get("session_id")
    roots = (
        payload.get("workspacePaths", [])
        if host == "antigravity"
        else payload.get("workspace_roots", [])
        if host == "cursor"
        else [payload.get("cwd")]
    )
    if not isinstance(identity, str) or not roots or not all(isinstance(p, str) for p in roots):
        return {}
    owner = f"{host}:{identity}"
    if event in {"SessionStart", "sessionStart", "UserPromptSubmit"}:
        context = (
            "For requested TUM course authoring, declare the whole batch and immediately run "
            f"tum-mcp study task start PROJECT --batch ID --owner {shlex.quote(owner)}. "
            "Only add --review-rounds N when review was already authorized. Determine source "
            "coverage before drafting; finish every requested workspace and internal check. "
            f"Use --owner {shlex.quote(owner)} with study task finish or pause as well. "
            "Finish the task before the final report. Ordinary course questions need no task."
        )
        if host == "cursor":
            return {"env": {"TUM_MCP_TASK_OWNER": owner}, "additional_context": context}
        if host == "antigravity":
            return {"injectSteps": [{"systemMessage": {"systemMessage": context}}]}
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}
    interrupted = event in {"Interrupt", "SessionEnd", "sessionEnd", "StopFailure"}
    if host == "cursor" and payload.get("status", "completed") != "completed":
        interrupted = True
    if host == "antigravity":
        if payload.get("fullyIdle") is not True:
            return {}
        interrupted = payload.get("terminationReason") != "model_stop"
    if host == "claude" and payload.get("background_tasks") and not interrupted:
        return {}
    result = tasks.stop(
        {
            "session_id": owner,
            "cwd": roots[0],
            "workspace_roots": roots,
            "hook_event_name": "Interrupt" if interrupted else "Stop",
        }
    )
    if host == "cursor":
        return {"followup_message": result["reason"]} if result.get("decision") == "block" else {}
    if host == "antigravity":
        return (
            {"decision": "continue", "reason": result["reason"]}
            if result.get("decision") == "block"
            else {"decision": "stop"}
        )
    return result
