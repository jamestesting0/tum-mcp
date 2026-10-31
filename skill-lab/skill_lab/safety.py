"""Trial boundaries: guarded variant paths, blocked commands and tools, redaction, scans."""

import fnmatch
import hashlib
import json
import re
from pathlib import Path

GUARDED_PATHS = (
    "src/tum_mcp/moodle/*",
    "src/tum_mcp/tumonline/*",
    "src/tum_mcp/artemis/*",
    "src/tum_mcp/zulip/*",
    "src/tum_mcp/tum_live/*",
    "src/tum_mcp/transport.py",
    "src/tum_mcp/server.py",
    "src/tum_mcp/credentials*",
    "src/tum_mcp/client_*",
    "src/tum_mcp/clients.py",
    "src/tum_mcp/legacy_clients.py",
    "src/tum_mcp/lifecycle_cli.py",
    "src/tum_mcp/updates.py",
    "src/tum_mcp/uninstall.py",
    "src/tum_mcp/settings.py",
    "src/tum_mcp/*session*",
    "src/tum_mcp/*keyring*",
    "src/tum_mcp/*vault*",
    "npm/*",
    ".github/*",
    "skill-lab/*",
    "AGENTS.md",
    "package.json",
    "pyproject.toml",
)

BLOCKED_TOOLS = frozenset(
    {
        "tum_logout",
        "tum_connect",
        "moodle_login",
        "moodle_logout",
        "moodle_clear_cache",
        "zulip_save_checkpoint",
    }
)

REDACTED_TOOL_PATTERNS = (
    "tumonline_*",
    "zulip_search_messages",
    "zulip_read_topic",
    "zulip_get_message",
    "moodle_list_personal_records",
    "moodle_read_personal_record",
    "moodle_list_discussions",
    "moodle_read_discussion",
    "artemis_get_feedback",
    "tum_status",
    "tum_get_preferences",
    "tum_capabilities",
)

CREDENTIAL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"MoodleSession[A-Za-z0-9]*=\w{8,}",
        r"_shibsession_\w*=\w{8,}",
        r"shib_idp_session=\w{8,}",
        r"JSESSIONID=\w{16,}",
        r"Bearer\s+[A-Za-z0-9._\-]{24,}",
        r"\"(?:password|passwd|api_key|apikey|client_secret)\"\s*:\s*\"[^\"]{4,}\"",
        r"sk-(?:ant-)?[A-Za-z0-9_\-]{24,}",
    )
)


def patch_paths(patch: str) -> list[str]:
    paths: set[str] = set()
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            paths.update(part[2:] for part in parts[2:4] if part[:2] in {"a/", "b/"})
        elif line.startswith(("+++ b/", "--- a/")):
            paths.add(line[6:].strip())
    return sorted(path for path in paths if path and path != "/dev/null")


def guarded(paths: list[str]) -> list[str]:
    return [
        path for path in paths if any(fnmatch.fnmatch(path, pattern) for pattern in GUARDED_PATHS)
    ]


def tool_name(raw: str) -> str:
    for prefix in ("mcp__tum__", "tum__", "tum."):
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return raw


def should_redact(raw_tool: str) -> bool:
    name = tool_name(raw_tool)
    return any(fnmatch.fnmatch(name, pattern) for pattern in REDACTED_TOOL_PATTERNS)


def placeholder(value: object) -> dict[str, object]:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    data = text.encode("utf-8", "replace")
    return {"redacted": True, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()[:16]}


def sensitive_strings(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict | list):
            return sensitive_strings(parsed)
        text = value.strip()
        distinctive = any(c.isupper() or c.isdigit() for c in text) or len(text.split()) > 1
        if len(text) >= 4 and distinctive:
            found.add(text)
    elif isinstance(value, dict):
        for item in value.values():
            found |= sensitive_strings(item)
    elif isinstance(value, list):
        for item in value:
            found |= sensitive_strings(item)
    elif isinstance(value, int) and abs(value) >= 10_000:
        found.add(str(value))
    return found


def scrub(value: object, secrets: list[str]) -> object:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, dict):
        return {key: scrub(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, secrets) for item in value]
    return value


def scrub_echoes(events: list[dict], found: set[str]) -> list[dict]:
    secrets = sorted(found, key=len, reverse=True)
    return [scrub(event, secrets) for event in events] if secrets else events


def redact_claude(events: list[dict]) -> list[dict]:
    found: set[str] = set()
    names: dict[str, str] = {}
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        redacted_here = False
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                names[str(block.get("id"))] = str(block.get("name", ""))
            elif block.get("type") == "tool_result":
                if should_redact(names.get(str(block.get("tool_use_id")), "")):
                    found |= sensitive_strings(block.get("content"))
                    block["content"] = placeholder(block.get("content"))
                    redacted_here = True
        if redacted_here and "tool_use_result" in event:
            found |= sensitive_strings(event["tool_use_result"])
            event["tool_use_result"] = placeholder(event["tool_use_result"])
    return scrub_echoes(events, found)


def redact_codex(events: list[dict]) -> list[dict]:
    found: set[str] = set()
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        if should_redact(str(item.get("tool", ""))):
            for key in ("result", "output", "content"):
                if key in item:
                    found |= sensitive_strings(item[key])
                    item[key] = placeholder(item[key])
    return scrub_echoes(events, found)


def credential_hits(text: str) -> list[str]:
    return [pattern.pattern for pattern in CREDENTIAL_PATTERNS if pattern.search(text)]


def scan_tree(root: Path, *, limit_bytes: int = 2_000_000) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.stat().st_size > limit_bytes:
            continue
        if path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip"}:
            continue
        found = credential_hits(path.read_text(encoding="utf-8", errors="ignore"))
        hits.extend(f"{path.relative_to(root)}: {pattern}" for pattern in found)
    return hits
