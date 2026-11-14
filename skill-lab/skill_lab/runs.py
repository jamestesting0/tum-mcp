"""One trial run: an empty (or checkpointed) folder, a simulated student, a variant, a host."""

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import threading
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
BROKER_SECONDS = 2400
EXPIRED_MESSAGE = "A campus session expired during the run; run `tum-mcp login`, then repeat it."


def _broker_command(python: Path, arguments: list[str]) -> list[str]:
    return [str(python), "-I", "-m", "tum_mcp", *arguments]


RENDER_OPTIONS = frozenset({"--exam", "--gallery", "--phone", "--interact", "--learner", "--json"})
PACKET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,80}$")
STEM = re.compile(r"[0-9]{2}_[a-z0-9][a-z0-9-]{0,80}")


def _render_request(
    job: dict, workspace: Path, checker: list[str] | None = None
) -> tuple[list[str], Path]:
    arguments = job["arguments"]
    cwd = Path(job["cwd"]).resolve()
    command = arguments[:2]
    if not cwd.is_relative_to(workspace) or command not in (
        ["study", "visuals"],
        ["review", "run-checker"],
        ["lecture", "prepare"],
        ["audio-notes", "listen"],
        ["video-notes", "listen"],
    ):
        raise LabError(
            "The broker only runs study visuals, review run-checker, lecture prepare and "
            "media listen inside its trial workspace."
        )
    if len(arguments) < 3 or arguments[2].startswith("-"):
        raise LabError("A broker request names its course project.")
    project = (cwd / arguments[2]).resolve()
    if not project.is_relative_to(workspace):
        raise LabError("A broker request's project stays inside its trial workspace.")
    options = iter(arguments[3:])
    if command[1] == "listen":
        # Speech recognition uses the GPU, which the trial sandbox blocks.
        if len(arguments) != 4 or not STEM.fullmatch(arguments[3]):
            raise LabError("A listen request names its project and one published stem.")
        return arguments, cwd
    if command == ["lecture", "prepare"]:
        recordings = 0
        for option in options:
            if option == "--previews":
                continue
            value = next(options, "")
            pattern = {
                "--recording": r"https://live\.rbg\.tum\.de/w/[A-Za-z0-9_-]{1,100}/[1-9][0-9]{0,15}",
                "--language": r"[a-z]{2,3}",
                "--frame-at": r"[0-9]{1,7}(?:\.[0-9]{1,6})?",
            }.get(option)
            if pattern is None or re.fullmatch(pattern, value) is None:
                raise LabError(
                    "Lecture preparation accepts canonical recording URLs, language, "
                    "frame times and --previews only."
                )
            recordings += option == "--recording"
        if not recordings:
            raise LabError("Lecture preparation names at least one selected recording.")
        return arguments, cwd
    if command == ["study", "visuals"]:
        for option in options:
            if option in {"--unit", "--exercise"}:
                value = next(options, "")
                if not value or value.startswith("-"):
                    raise LabError("A render selection needs a unit or exercise key.")
            elif option not in RENDER_OPTIONS:
                raise LabError("The render broker received an unsupported option.")
        return arguments, cwd
    # A fresh checker: the trial names only what to check; the lab picks the read-only command,
    # with the trial's own host and model, so a trial cannot run anything else on the host.
    if checker is None:
        raise LabError("This trial has no fresh checker.")
    chosen: list[str] = []
    for option in options:
        if option == "--packet":
            value = next(options, "")
            if not PACKET.match(value):
                raise LabError("A checker request names a packet id from review next.")
            chosen += [option, value]
        elif option == "--plans":
            chosen.append(option)
        else:
            raise LabError("A checker request names only --packet ID or --plans.")
    return [*arguments[:3], *chosen, "--command", shlex.join(checker)], cwd


def render_broker(
    folder: Path,
    python: Path,
    checker: list[str] | None = None,
    environment: dict[str, str] | None = None,
) -> threading.Event:
    """Serve vetted checks and recording preparation outside the author's sandbox.

    Each request names a workspace-bound command; its result is written beside it.
    Returns the event that stops the server.
    """
    stop = threading.Event()

    def handle(request: Path, job: dict) -> None:
        started = datetime.now(UTC).isoformat()
        try:
            observed = checker
            if checker and job["arguments"][:2] == ["review", "run-checker"]:
                kind = "plan_check" if "--plans" in job["arguments"] else "review_packet"
                log = request.with_name(request.name.replace(".request.json", ".sessions.jsonl"))
                observed = [
                    str(python), "-I", str(LAB_CODE / "shim.py"),
                    "--lab-checker", str(log), kind, *checker,
                ]  # fmt: skip
            arguments, cwd = _render_request(job, folder.parent.resolve(), observed)
            done = subprocess.run(  # noqa: S603 - workspace-bound vetted command only
                _broker_command(python, arguments),
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=BROKER_SECONDS,
                check=False,
            )
            result = {"code": done.returncode, "stdout": done.stdout, "stderr": done.stderr}
        except (LabError, subprocess.TimeoutExpired) as error:
            result = {"code": 2, "stdout": "", "stderr": str(error)}
        result.update(
            started=started,
            ended=datetime.now(UTC).isoformat(),
            arguments=job["arguments"],
        )
        response = request.with_name(request.name.replace(".request.", ".response."))
        staged = response.with_suffix(".tmp")
        staged.write_text(json.dumps(result), encoding="utf-8")
        staged.replace(response)

    def serve() -> None:
        # Each request runs on its own thread: a render never waits behind a long checker,
        # and a round's checkers run side by side.
        while not stop.wait(1):
            for request in sorted(folder.glob("*.request.json")):
                job = json.loads(request.read_text(encoding="utf-8"))
                request.unlink()
                threading.Thread(target=handle, args=(request, job), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return stop


def storage_environment(downloads: Path) -> dict[str, str]:
    from skill_lab.install_variant import client_module

    environment = dict(client_module("hosts").storage_environment())
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
    for project in projects(workspace):
        path = project / ".tum-mcp/task.json"
        if path.is_file():
            task = json.loads(path.read_text(encoding="utf-8"))
            if task.get("phase") in {"pending", "ready"}:
                task.update(
                    phase="paused",
                    reason="Restored skill-lab checkpoint; previous session ownership is inactive.",
                )
                path.write_text(json.dumps(task, indent=2), encoding="utf-8")


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
    plant: bool = False,
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
        original = json.loads((source[0].parent / "run.json").read_text(encoding="utf-8"))
        previous = paths.round_dir(original["round"]) / "variants" / original["variant"]
        refusal = scenarios.checkpoint_refusal(
            scenario, start, variants.changed_inputs(previous, variant_dir)
        )
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
            plant=plant,
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
    *,
    plant: bool = False,
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
    if plant:
        from skill_lab import calibrate

        planted = calibrate.plant(workspace)
        (run_dir / "planted.json").write_text(json.dumps(planted, indent=2), encoding="utf-8")
    shim = bin_dir / "tum-mcp"
    broker = workspace / ".lab-broker"
    shim.write_text(
        f'#!/bin/sh\nSKILL_LAB_RENDER_BROKER="{broker}" exec "{python}" -I '
        f'"{LAB_CODE / "shim.py"}" "$@"\n',
        encoding="utf-8",
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
        "speed_tier": spec.tier or "standard",
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
    environment = hosts.clean_environment(storage_environment(downloads), home, bin_dir, spec.host)
    serving = render_broker(broker, python, hosts.checker_command(spec), environment)
    try:
        installer(variant_dir, spec.host, home, downloads)
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
                question_text = result.student_questions or result.text
                asked_student = bool(result.student_questions) or scenarios.asks_student(
                    result.text
                )
                entry.setdefault("parts", []).append(
                    {
                        "label": label,
                        "seconds": round(time.monotonic() - clock, 1),
                        "model_reported": result.model_reported,
                        "usage": result.usage,
                        "cost_usd": result.cost_usd,
                        "error": result.error if result.is_error else "",
                        "ended_with_question": asked_student,
                    }
                )
                raw_text = (run_dir / "raw" / f"{label}.jsonl").read_text(encoding="utf-8")
                if any(marker in raw_text for marker in SESSION_EXPIRED_MARKERS):
                    result.is_error = True
                    result.error = EXPIRED_MESSAGE
                if result.is_error:
                    break
                reply = scenario.reply_to(question_text) if asked_student else None
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
        serving.set()
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
