"""Lab host profiles: an isolated HOME per host, logged in once by the human."""

import json
import subprocess

from skill_lab import LabError, hosts, models, paths


def create(host: str) -> str:
    home = paths.profile_home(host)
    home.mkdir(parents=True, exist_ok=True)
    if host == "claude":
        return f'CLAUDE_CONFIG_DIR="{home}" claude auth login'
    return f'HOME="{home}" codex login'


def host_login(host: str, *, offline: bool = False) -> tuple[bool, str]:
    home = paths.profile_home(host)
    if not home.is_dir():
        return False, "profile missing; run `lab profile create`"
    environment = hosts.clean_environment({}, home, None, host, offline=offline)
    if host == "codex":
        result = subprocess.run(
            ["codex", "login", "status"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        text = (result.stdout + result.stderr).strip()
        expected = "logged in using chatgpt" if offline else "logged in"
        return result.returncode == 0 and text.lower().startswith(expected), (
            text.splitlines()[0] if text else ""
        )
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
    from skill_lab.runs import campus_states

    ok, detail = host_login(host)
    return {
        "host": host,
        "login": ok,
        "detail": detail,
        "models": sorted(models.available(host, paths.profile_home(host))),
        "campus": campus_states(),
    }


def require_offline_login() -> None:
    try:
        ready, _ = host_login("codex", offline=True)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise LabError("The isolated Codex profile cannot check its ChatGPT login.") from error
    if not ready:
        raise LabError("The isolated Codex profile must already be logged in through ChatGPT.")
