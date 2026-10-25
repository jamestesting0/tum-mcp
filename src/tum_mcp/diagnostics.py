"""Read-only local diagnostics, with explicitly requested live authentication checks."""

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError

from tum_mcp import __version__
from tum_mcp.client_hosts import ClientHost, client_home
from tum_mcp.clients import CLIENTS, client_config_path, read_client_config
from tum_mcp.errors import CampusError
from tum_mcp.moodle.browsers import BrowserSetupError, discover_browsers, is_wsl
from tum_mcp.moodle.platforms import data_root
from tum_mcp.settings import Frozen, Preferences, Provider, config_path, data_path
from tum_mcp.skills import inspect_skills
from tum_mcp.ui import State


class Check(Frozen):
    label: str
    state: State
    detail: str
    location: str | None = None


class DoctorReport(Frozen):
    schema_version: int = 1
    version: str = __version__
    platform: str
    services: tuple[Check, ...]
    clients: tuple[Check, ...]
    runtime: tuple[Check, ...]
    next_steps: tuple[str, ...]
    data_directory: str
    config_directory: str
    live_authentication: str
    remote_actions: str = "disabled"


def github_check(*, live: bool) -> Check:
    """Check the optional publishing prerequisite without reading credential files."""
    executable = shutil.which("gh")
    if executable is None:
        return Check(
            label="GitHub publishing",
            state=State.MISSING,
            detail="Optional: install GitHub CLI, then gh auth login --hostname github.com.",
        )
    if not live:
        return Check(
            label="GitHub publishing",
            state=State.CONFIGURED,
            location=executable,
            detail="GitHub CLI found; authentication not checked. Use doctor --live to verify.",
        )
    from tum_mcp.study_github import Account, GitHub

    try:
        account = GitHub(executable).require("user", Account)
        return Check(
            label="GitHub publishing",
            state=State.READY,
            location=executable,
            detail=f"Authenticated as {account.login}; repository/Pages permissions "
            "and paid-plan eligibility are checked at publication.",
        )
    except CampusError as error:
        return Check(label="GitHub publishing", state=State.ACTION, detail=error.message)


def collect_diagnostics(*, live: bool = False, home: Path | None = None) -> DoctorReport:
    base = home or Path.home()
    data = data_path()
    config = config_path()
    settings = config / "preferences.json"
    next_steps: list[str] = []
    runtime: list[Check] = []
    try:
        prefs = (
            Preferences.model_validate_json(settings.read_bytes())
            if settings.exists()
            else Preferences()
        )
    except (ValidationError, OSError):
        prefs = Preferences()
        runtime.append(
            Check(
                label="Preferences",
                state=State.FAILED,
                detail="Invalid configuration; repair preferences.json locally.",
            )
        )
    services: list[Check] = []
    moodle_root = data_root()
    moodle_session = moodle_root / "local-session/session.enc"
    moodle_key = moodle_root / "local-session/session.key"
    if moodle_session.is_file() and moodle_key.is_file():
        check = Check(
            label="Moodle",
            state=State.CONFIGURED,
            detail="Local encrypted session saved; live authentication not checked.",
        )
        if live:
            from tum_mcp.moodle.auth import SessionStore
            from tum_mcp.moodle.config import Paths
            from tum_mcp.moodle.errors import MoodleError
            from tum_mcp.moodle.http_client import MoodleHTTP

            try:
                MoodleHTTP(SessionStore(Paths(moodle_root), storage="file")).get("/my/courses.php")
                check = Check(
                    label="Moodle",
                    state=State.READY,
                    detail="Live session verified; Moodle read tools available.",
                )
            except MoodleError as error:
                check = Check(label="Moodle", state=State.ACTION, detail=error.message)
    else:
        legacy = (moodle_root / "session.enc").is_file()
        detail = (
            "Legacy native-store session retained; reconnect for local-file storage."
            if legacy
            else "No local session. Connect to enable Moodle reads."
        )
        check = Check(label="Moodle", state=State.ACTION, detail=detail)
    services.append(check)
    needs_connection = check.state == State.ACTION
    for provider in Provider:
        accounts = [a for a in prefs.accounts if a.provider == provider]
        if not accounts:
            needs_connection = True
            services.append(
                Check(
                    label=provider.value.title(),
                    state=State.ACTION,
                    detail="No account configured. Run tum-mcp connect.",
                )
            )
        for index, account in enumerate(accounts):
            label = provider.value.title() + (f" {index + 1}" if len(accounts) > 1 else "")
            path = data / "credentials/local" / f"{account.id}.enc"
            key = data / "credentials/local/session.key"
            scopes = len(account.courses) if provider == Provider.ARTEMIS else len(account.channels)
            unit = "courses" if provider == Provider.ARTEMIS else "channels"
            saved = path.is_file() and key.is_file()
            needs_connection |= not saved
            state = State.CONFIGURED if saved else State.ACTION
            detail = (
                f"Saved locally; {scopes} enabled {unit}. Live authentication not checked."
                if saved
                else "Reconnect for local encrypted storage; any legacy session is retained."
            )
            if live and saved:
                from tum_mcp.artemis import Artemis
                from tum_mcp.transport import API
                from tum_mcp.zulip import Zulip

                try:
                    api = API(account)
                    if provider == Provider.ARTEMIS:
                        Artemis(api).identity()
                    else:
                        Zulip(api).identity()
                    state = State.READY if scopes else State.ACTION
                    detail = (
                        f"Live identity verified; {scopes} enabled {unit}."
                        if scopes
                        else f"Live identity verified; choose {unit} with tum-mcp scope."
                    )
                except CampusError as error:
                    state, detail = State.ACTION, error.message
                    needs_connection = True
            elif saved and not scopes:
                state, detail = State.ACTION, f"Saved session; choose {unit} with tum-mcp scope."
            services.append(Check(label=label, state=state, detail=detail))
            if saved and not scopes:
                next_steps.append(
                    f"tum-mcp discover {provider.value} ACCOUNT_ID"
                    f" — choose {unit}, then use scope; status shows IDs"
                )
    if needs_connection:
        next_steps.append("tum-mcp connect — sign in only to the services you select")

    clients: list[Check] = []
    profiles = [(ClientHost.LOCAL, base)]
    if is_wsl():
        try:
            profiles.append((ClientHost.WINDOWS, client_home(ClientHost.WINDOWS)))
        except BrowserSetupError as error:
            runtime.append(Check(label="Windows clients", state=State.ACTION, detail=error.message))
    for host, profile in profiles:
        for name in CLIENTS:
            path = (
                config / "mcp.json"
                if name == "generic" and host == ClientHost.LOCAL
                else client_config_path(name, profile, host=host)
            )
            try:
                entry = read_client_config(path).mcpServers.get("tum")
                registered = isinstance(entry, dict) and (
                    isinstance(entry.get("command"), str)
                    and bool(entry.get("command"))
                    or isinstance(entry.get("url"), str)
                    and bool(entry.get("url"))
                )
                detail = (
                    "MCP registration saved; host activation not checked."
                    if registered
                    else f"Register with tum-mcp setup --client {name}"
                    + (" --host windows." if host == ClientHost.WINDOWS else ".")
                )
                state = State.CONFIGURED if registered else State.UNCONFIGURED
                if entry is not None and not registered:
                    state, detail = (
                        State.FAILED,
                        "Invalid tum server entry; review client configuration.",
                    )
            except CampusError as error:
                detail, state = error.message, State.FAILED
            clients.append(
                Check(
                    label=name.title() + (" (Windows)" if host == ClientHost.WINDOWS else ""),
                    state=state,
                    detail=detail,
                    location=str(path),
                )
            )
    if not any(item.state == State.CONFIGURED for item in clients):
        next_steps.append("tum-mcp setup --client codex — or claude, cursor, antigravity, generic")

    runtime.append(
        Check(
            label="Python",
            state=State.READY,
            detail=f"{platform.python_version()} · current interpreter",
            location=sys.executable,
        )
    )
    try:
        browsers = discover_browsers()
        runtime.append(
            Check(
                label="Browsers",
                state=State.READY if browsers else State.MISSING,
                detail=(
                    "Detected: "
                    + ", ".join(browser.label for browser in browsers)
                    + ". Launch not checked."
                )
                if browsers
                else "Install a Chromium browser such as Edge, Chrome, Brave or Chromium.",
            )
        )
        if not browsers:
            next_steps.append("Install a Chromium browser before connecting services.")
        if is_wsl():
            runtime.append(
                Check(
                    label="WSL browser bridge",
                    state=State.INFO,
                    detail="Windows sign-in through private pipes; "
                    "the isolated runtime is prepared on first use.",
                )
            )
    except BrowserSetupError as error:
        runtime.append(Check(label="Browsers", state=State.ACTION, detail=error.message))
    node = shutil.which("node")
    node_state, node_detail = (
        State.MISSING,
        "Install Node.js 22.14+ for npm and the Codex launcher.",
    )
    if node:
        try:
            result = subprocess.run(  # noqa: S603
                [node, "--version"], capture_output=True, timeout=3, check=False, text=True
            )
            version = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\s*", result.stdout)
            if version and result.returncode == 0:
                supported = tuple(int(part) for part in version.groups()) >= (22, 14, 0)
                node_state = State.READY if supported else State.ACTION
                node_detail = (
                    f"{version.group().strip()} · supported npm runtime."
                    if supported
                    else "Upgrade Node.js to 22.14 or newer."
                )
            else:
                node_state, node_detail = (
                    State.ACTION,
                    "Found Node.js; version could not be verified.",
                )
        except (subprocess.SubprocessError, OSError, UnicodeError):
            node_state, node_detail = State.ACTION, "Found Node.js; version check failed."
    runtime.append(Check(label="Node.js", state=node_state, detail=node_detail, location=node))
    github = github_check(live=live)
    runtime.append(github)
    if github.state in {State.MISSING, State.ACTION}:
        next_steps.append(
            "Optional website publishing: install GitHub CLI if needed, then "
            "gh auth login --hostname github.com and tum-mcp doctor --live."
        )
    try:
        skills = inspect_skills()
        runtime.append(
            Check(
                label="Workflow skills",
                state=State.READY,
                detail=f"{len(skills)} valid definitions; host selection quality not measured.",
            )
        )
    except CampusError as error:
        runtime.append(Check(label="Workflow skills", state=State.FAILED, detail=error.message))
    except (OSError, UnicodeError):
        runtime.append(
            Check(
                label="Workflow skills",
                state=State.FAILED,
                detail="Skill files are unreadable; review local customizations before setup.",
            )
        )
    runtime.append(
        Check(
            label="Credential storage",
            state=State.INFO,
            detail="Encrypted files, owner-restricted key; less protection than a native keychain.",
        )
    )
    return DoctorReport(
        platform=f"{platform.system()} {platform.machine()}",
        services=tuple(services),
        clients=tuple(clients),
        runtime=tuple(runtime),
        next_steps=tuple(dict.fromkeys(next_steps)),
        data_directory=str(data),
        config_directory=str(config),
        live_authentication="checked_saved_local_sessions" if live else "not_checked",
    )
