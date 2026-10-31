"""One trial run: an empty (or checkpointed) folder, a simulated student, a variant, a host."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from skill_lab import LabError, hosts, models, paths, rounds, safety, scenarios, variants
from skill_lab.models import ModelSpec

LAB_CODE = Path(__file__).resolve().parent
GIT_IDENTITY = ("-c", "user.name=skill-lab", "-c", "user.email=skill-lab@localhost")
HOST_LOGS = {
    "claude": ("projects", "todos", "shell-snapshots"),
    "codex": (".codex/sessions", ".codex/archived_sessions", ".codex/history.jsonl", ".codex/log"),
}

Installer = Callable[[Path, str, Path, Path], None]
SESSION_EXPIRED_MARKERS = ("SESSION_EXPIRED",)
EXPIRED_MESSAGE = "A campus session expired during the run; run `tum-mcp login`, then repeat it."


def storage_environment(downloads: Path) -> dict[str, str]:
    from tum_mcp.client_hosts import storage_environment as real

    environment = dict(real())
    environment["TUM_MOODLE_DOWNLOAD_DIR"] = str(downloads)
    return environment


def campus_states() -> dict[str, str]:
    environment = {**os.environ, **storage_environment(paths.state() / "check-downloads")}
    result = subprocess.run(
        [sys.executable, "-I", "-m", "tum_mcp", "doctor", "--json", "--live"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except ValueError:
        return {"error": result.stderr.strip()[-200:]}
    return {
        str(item["label"]): str(item.get("state"))
        for item in report.get("services", [])
        if isinstance(item, dict) and item.get("label")
    }


def require_moodle(states: dict[str, str]) -> None:
    if states.get("Moodle") != "Ready":
        raise LabError(
            f"Moodle is {states.get('Moodle', 'unknown')!r}, not Ready; run `tum-mcp login`, "
            "select Moodle, then start the run again."
        )


def install(variant_dir: Path, host: str, home: Path, downloads: Path) -> None:
    command = [
        str(variants.python_of(variant_dir)),
        "-I",
        str(LAB_CODE / "install_variant.py"),
        "--host",
        host,
        "--home",
        str(home),
        "--proxy",
        str(LAB_CODE / "mcp_proxy.py"),
        "--block",
        ",".join(sorted(safety.BLOCKED_TOOLS)),
        "--downloads",
        str(downloads),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise LabError(f"Installing the variant failed: {result.stderr.strip()[-600:]}")


def git(history: Path, workspace: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *GIT_IDENTITY, f"--git-dir={history}", f"--work-tree={workspace}", *arguments],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def snapshot(history: Path, workspace: Path, turn: int) -> None:
    git(history, workspace, "add", "-A", ".")
    git(history, workspace, "commit", "-q", "--allow-empty", "-m", f"after turn {turn}")
    git(history, workspace, "tag", "-f", f"turn-{turn}")


def parse_checkpoint(text: str, round_id: str) -> tuple[Path, int]:
    if "@" not in text:
        raise LabError("Checkpoints look like base-1@1 or r0/base-1@1.")
    run_ref, turn_text = text.rsplit("@", 1)
    source_round, run_id = run_ref.split("/", 1) if "/" in run_ref else (round_id, run_ref)
    history = paths.round_dir(source_round) / "runs" / run_id / "history.git"
    if not history.is_dir() or not turn_text.isdigit():
        raise LabError(f"Checkpoint {text} does not name a finished run and turn.")
    return history, int(turn_text)


def restore(history: Path, turn: int, workspace: Path) -> None:
    archive = subprocess.run(
        ["git", f"--git-dir={history}", "archive", "--format=tar", f"turn-{turn}"],
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(workspace, filter="data")


def projects(workspace: Path) -> list[Path]:
    found = []
    for state in sorted(workspace.glob("**/.tum-mcp/state.json")):
        if len(state.relative_to(workspace).parts) <= 5:
            found.append(state.parent.parent)
    return found


def inventory_hash(workspace: Path) -> str | None:
    found = projects(workspace)
    if not found:
        return None
    digest = hashlib.sha256()
    for path in sorted((found[0] / "materials").rglob("*")):
        if path.is_file():
            relative = path.relative_to(found[0]).as_posix()
            digest.update(f"{relative}\0{path.stat().st_size}\n".encode())
    return digest.hexdigest()


def next_run_id(round_id: str, variant: str) -> str:
    """Claim the next free id by creating its folder, so simultaneous runs never share one."""
    root = paths.round_dir(round_id) / "runs"
    root.mkdir(parents=True, exist_ok=True)
    number = 1
    while True:
        try:
            (root / f"{variant}-{number}").mkdir()
        except FileExistsError:
            number += 1
            continue
        return f"{variant}-{number}"


def finalize_transcripts(run_dir: Path, host: str) -> list[str]:
    raw, transcript = run_dir / "raw", run_dir / "transcript"
    transcript.mkdir(exist_ok=True)
    for path in sorted(raw.glob("*.jsonl")) if raw.is_dir() else []:
        events = hosts.parse_lines(path.read_text(encoding="utf-8", errors="replace"))
        events = safety.redact_claude(events) if host == "claude" else safety.redact_codex(events)
        lines = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
        (transcript / path.name).write_text(lines, encoding="utf-8")
    shutil.rmtree(raw, ignore_errors=True)
    hits = safety.scan_tree(transcript)
    workspace = run_dir / "workspace"
    hits += [f"workspace/{hit}" for hit in safety.scan_tree(workspace)]
    return hits


def clear_host_logs(home: Path, host: str) -> None:
    for relative in HOST_LOGS[host]:
        target = home / relative
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()


def write_record(run_dir: Path, record: dict) -> None:
    (run_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def execute(
    round_id: str,
    variant_name: str,
    *,
    author: ModelSpec | None = None,
    scenario_id: str | None = None,
    checkpoint: str | None = None,
    confirm: bool = False,
    installer: Installer = install,
    python: Path | None = None,
    campus_check: Callable[[], None] = lambda: require_moodle(campus_states()),
) -> dict:
    config = rounds.load(round_id)
    spec = author or ModelSpec.from_dict(config["roles"]["author"])
    if author is None:
        models.validate(spec, role="author", profile_home=paths.profile_home(spec.host))
    if scenario_id is None:
        scenario_id = config["confirm_scenario"] if confirm else config["scenario"]
    if not scenario_id:
        raise LabError("This round has no confirmation scenario; pass --scenario.")
    scenario = scenarios.load(scenario_id)
    variant_dir = paths.round_dir(round_id) / "variants" / variant_name
    if not (variant_dir / "variant.json").is_file():
        raise LabError(f"Variant {variant_name} does not exist; create it with `lab variant`.")
    start = 0
    source: tuple[Path, int] | None = None
    if checkpoint:
        source = parse_checkpoint(checkpoint, round_id)
        start = source[1]
        refusal = scenarios.checkpoint_refusal(scenario, start, variants.touched_paths(variant_dir))
        if refusal:
            raise LabError(f"Checkpoint refused: {refusal}")
    campus_check()
    timeout = int(config["budget"]["turn_timeout_min"]) * 60
    # A trial installs into, and clears the logs of, its host's profile, so one host runs one
    # trial at a time; Claude and Codex trials run side by side.
    lock = FileLock(str(paths.state() / f"live-{spec.host}.lock"))
    paths.state().mkdir(parents=True, exist_ok=True)
    try:
        lock.acquire(timeout=0)
    except Timeout as error:
        raise LabError(
            f"Another live {spec.host} trial is running; each host runs one at a time."
        ) from error
    try:
        # Both hosts may start together; the round lock keeps the budget count and ids exact.
        with FileLock(str(paths.round_dir(round_id) / "runs.lock")):
            rounds.check_budget(round_id, "runs")
            run_id = next_run_id(round_id, variant_name)
        return _run(
            round_id,
            run_id,
            variant_name,
            variant_dir,
            spec,
            scenario,
            start,
            source,
            confirm,
            checkpoint,
            timeout,
            installer,
            python or variants.python_of(variant_dir),
        )
    finally:
        lock.release()


def _run(
    round_id: str,
    run_id: str,
    variant_name: str,
    variant_dir: Path,
    spec: ModelSpec,
    scenario: scenarios.Scenario,
    start: int,
    source: tuple[Path, int] | None,
    confirm: bool,
    checkpoint: str | None,
    timeout: int,
    installer: Installer,
    python: Path,
) -> dict:
    run_dir = paths.round_dir(round_id) / "runs" / run_id
    downloads, bin_dir = run_dir / "downloads", run_dir / "bin"
    for directory in (downloads, bin_dir, run_dir / "raw"):
        directory.mkdir(parents=True)
    workspace = paths.workspaces() / round_id / run_id
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    (run_dir / "workspace").symlink_to(workspace, target_is_directory=True)
    history = run_dir / "history.git"
    subprocess.run(["git", "init", "-q", "--bare", str(history)], check=True)
    if source:
        restore(*source, workspace)
    shim = bin_dir / "tum-mcp"
    shim.write_text(
        f'#!/bin/sh\nexec "{python}" -I "{LAB_CODE / "shim.py"}" "$@"\n', encoding="utf-8"
    )
    shim.chmod(0o755)
    home = paths.profile_home(spec.host)
    home.mkdir(parents=True, exist_ok=True)
    record = {
        "id": run_id,
        "round": round_id,
        "variant": variant_name,
        "variant_spec": json.loads((variant_dir / "variant.json").read_text())["spec"],
        "author": str(spec),
        "scenario": scenario.id,
        "start_turn": start,
        "checkpoint": checkpoint,
        "confirm": confirm,
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "running",
        "turns": [],
    }
    write_record(run_dir, record)
    began = time.monotonic()
    try:
        installer(variant_dir, spec.host, home, downloads)
        environment = hosts.clean_environment(
            storage_environment(downloads), home, bin_dir, spec.host
        )
        if source:
            snapshot(history, workspace, start)
        session = None
        for number, turn in enumerate(scenario.turns[start:], start=start + 1):
            entry = {"turn": number, "message": turn.say, "replies": []}
            message, attempt = turn.say, 0
            while True:
                label = f"turn-{number}" + (f"-reply-{attempt}" if attempt else "")
                clock = time.monotonic()
                result = hosts.run_turn(
                    spec,
                    message,
                    workspace=workspace,
                    environment=environment,
                    session=session,
                    timeout=timeout,
                    raw=run_dir / "raw" / f"{label}.jsonl",
                )
                session = result.session_id or session
                entry.setdefault("parts", []).append(
                    {
                        "label": label,
                        "seconds": round(time.monotonic() - clock, 1),
                        "model_reported": result.model_reported,
                        "usage": result.usage,
                        "cost_usd": result.cost_usd,
                        "error": result.error if result.is_error else "",
                        "ended_with_question": scenarios.asks_student(result.text),
                    }
                )
                raw_text = (run_dir / "raw" / f"{label}.jsonl").read_text(encoding="utf-8")
                if any(marker in raw_text for marker in SESSION_EXPIRED_MARKERS):
                    result.is_error = True
                    result.error = EXPIRED_MESSAGE
                if result.is_error:
                    break
                reply = (
                    scenario.reply_to(result.text) if scenarios.asks_student(result.text) else None
                )
                if reply is None or attempt >= scenarios.MAX_REPLIES_PER_TURN:
                    break
                attempt += 1
                entry["replies"].append(reply)
                message = reply
            record["turns"].append(entry)
            snapshot(history, workspace, number)
            write_record(run_dir, record)
            if result.is_error:
                expired = result.error == EXPIRED_MESSAGE
                record["status"] = "campus-session-expired" if expired else "failed"
                record["error"] = result.error
                break
        else:
            record["status"] = "completed"
    except LabError as error:
        record["status"] = "failed"
        record["error"] = str(error)
    finally:
        record["minutes"] = round((time.monotonic() - began) / 60, 1)
        record["ended"] = datetime.now(UTC).isoformat(timespec="seconds")
        reported = {
            part.get("model_reported")
            for entry in record["turns"]
            for part in entry.get("parts", [])
            if part.get("model_reported")
        }
        record["models_reported"] = sorted(reported)
        if any(models.reported_matches(spec, name) is False for name in reported):
            record["status"] = "invalid-model"
        record["inventory_hash"] = inventory_hash(workspace)
        found = projects(workspace)
        record["project"] = str(found[0].relative_to(workspace)) if found else None
        hits = finalize_transcripts(run_dir, spec.host)
        clear_host_logs(home, spec.host)
        if hits:
            record["status"] = "quarantined"
            record["credential_hits"] = hits
        write_record(run_dir, record)
        if hits:
            quarantine = paths.state() / "quarantine" / f"{round_id}-{run_id}"
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            link = run_dir / "workspace"
            link.unlink()
            shutil.move(str(workspace), link)
            shutil.move(str(run_dir), quarantine)
            print(f"Run quarantined: possible credential text at {quarantine}", file=sys.stderr)
    return record
