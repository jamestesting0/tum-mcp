"""Lab host profiles: an isolated HOME per host, logged in once by the human."""

import json
import subprocess

from skill_lab import hosts, models, paths
from skill_lab.runs import campus_states


def create(host: str) -> str:
    home = paths.profile_home(host)
    home.mkdir(parents=True, exist_ok=True)
    if host == "claude":
        return f'CLAUDE_CONFIG_DIR="{home}" claude auth login'
    return f'HOME="{home}" codex login'


def host_login(host: str) -> tuple[bool, str]:
    home = paths.profile_home(host)
    if not home.is_dir():
        return False, "profile missing; run `lab profile create`"
    environment = hosts.clean_environment({}, home, None, host)
    if host == "codex":
        result = subprocess.run(
            ["codex", "login", "status"], env=environment, capture_output=True, text=True
        )
        text = (result.stdout + result.stderr).strip()
        return text.lower().startswith("logged in"), text.splitlines()[0] if text else ""
    result = subprocess.run(
        ["claude", "-p", "Reply with exactly OK", "--model", "haiku", "--output-format", "json"],
        env=environment,
        cwd=home,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return False, (result.stderr or result.stdout).strip()[:200]
    ok = not payload.get("is_error") and "OK" in str(payload.get("result", ""))
    return ok, "logged in" if ok else str(payload.get("result") or payload.get("subtype"))[:200]


def check(host: str) -> dict:
    ok, detail = host_login(host)
    return {
        "host": host,
        "login": ok,
        "detail": detail,
        "models": sorted(models.available(host, paths.profile_home(host))),
        "campus": campus_states(),
    }
