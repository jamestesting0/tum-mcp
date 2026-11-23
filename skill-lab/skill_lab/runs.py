"""One trial run: an empty (or checkpointed) folder, a simulated student, a variant, a host."""

import dataclasses
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from skill_lab import LabError, hosts, models, paths, profiles, rounds, safety, scenarios, variants
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
FAI_SLOTS = {
    ("base", scenarios.FAI_JOURNEY): 3,
    ("candidate", scenarios.FAI_JOURNEY): 2,
    ("candidate", scenarios.FAI_RESUME): 2,
}
LOOPBACK_NETWORK = (
    "(version 1) (allow default) (deny network*) "
    '(allow network* (local ip "localhost:*")) '
    "(allow network-bind (local unix-socket)) "
    '(allow network-outbound (remote ip "localhost:*"))'
)


def _broker_command(python: Path, arguments: list[str]) -> list[str]:
    return [str(python), "-I", "-m", "tum_mcp", *arguments]


RENDER_OPTIONS = frozenset({"--exam", "--gallery", "--phone", "--interact", "--learner", "--json"})
PACKET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,80}$")
BATCH_KEY = re.compile(r"[a-z0-9][a-z0-9_.-]{0,99}")
STEM = re.compile(r"[0-9]{2}_[a-z0-9][a-z0-9-]{0,80}")


def _render_request(
    job: dict, workspace: Path, checker: list[str] | None = None, *, offline: bool = False
) -> tuple[list[str], Path]:
    arguments = job["arguments"]
    cwd = Path(job["cwd"]).resolve()
    command = arguments[:2]
    if offline and command not in (["study", "visuals"], ["review", "run-checker"]):
        raise LabError("The offline broker only runs local browser checks and fresh checkers.")
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
            if option in {"--unit", "--exercise", "--lecture"}:
                value = next(options, "")
                if not value or value.startswith("-"):
                    raise LabError(f"Supply a key for {option}.")
            elif option not in RENDER_OPTIONS:
                raise LabError("The render broker received an unsupported option.")
        return arguments, cwd
    # A fresh checker: the trial names only what to check; the lab picks the read-only command,
    # with the trial's own host and model, so a trial cannot run anything else on the host.
    if checker is None:
        raise LabError("This trial has no fresh checker.")
    chosen: list[str] = []
    batch = False
    for option in options:
        if option == "--packet":
            value = next(options, "")
            if not PACKET.match(value):
                raise LabError("A checker request names a packet id from review next.")
            chosen += [option, value]
        elif option == "--plans":
            chosen.append(option)
        elif option == "--batch":
            value = next(options, "")
            if batch or not BATCH_KEY.fullmatch(value):
                raise LabError("A plan checker request accepts one canonical project batch key.")
            batch = True
            chosen += [option, value]
        else:
            raise LabError("A checker request names only --packet ID or --plans [--batch KEY].")
    if batch and ("--plans" not in chosen or "--packet" in chosen):
        raise LabError("A checker batch selector requires --plans without --packet.")
    return [*arguments[:3], *chosen, "--command", shlex.join(checker)], cwd


class OfflineBrokerTurn:
    """Own the offline broker's process groups and the run's checker allowance."""

    def __init__(self, limit: int, ledger: Path) -> None:
        self.limit = limit
        self.ledger = ledger
        self.failure: str | None = None
        self.deadline = 0.0
        self.lock = threading.Lock()
        self.active: set[subprocess.Popen[str]] = set()

    def remaining(self, deadline: float) -> float:
        if self.failure:
            raise LabError(self.failure)
        remaining = deadline - time.monotonic()
        if not deadline or deadline != self.deadline or remaining <= 0:
            raise LabError("The broker request has no active author turn.")
        return remaining

    def ledger_events(self) -> list[dict[str, str]]:
        if not self.ledger.exists():
            return []
        return [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines()]

    def finish(self) -> None:
        with self.lock:
            self.deadline = 0
            for process in self.active:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            self.active.clear()


def render_broker(
    folder: Path,
    python: Path,
    checker: list[str] | None = None,
    environment: dict[str, str] | None = None,
    *,
    turn: OfflineBrokerTurn | None = None,
) -> threading.Event:
    """Serve vetted checks and recording preparation outside the author's sandbox.

    Each request names a workspace-bound command; its result is written beside it.
    Returns the event that stops the server.
    """
    stop = threading.Event()

    def handle(request: Path, job: dict, deadline: float) -> None:
        started = datetime.now(UTC).isoformat()
        try:
            observed, log = checker, request
            is_checker = bool(checker and job["arguments"][:2] == ["review", "run-checker"])
            if is_checker and checker:
                kind = "plan_check" if "--plans" in job["arguments"] else "review_packet"
                log = request.with_name(request.name.replace(".request.json", ".sessions.jsonl"))
                observed = [
                    str(python), "-I", str(LAB_CODE / "shim.py"),
                    "--lab-checker", str(log), kind,
                    *(["--budget", str(turn.ledger), str(turn.limit)] if turn else []), *checker,
                ]  # fmt: skip
            arguments, cwd = _render_request(
                job, folder.parent.resolve(), observed, offline=turn is not None
            )
            command = _broker_command(python, arguments)
            if turn and arguments[:2] == ["study", "visuals"]:
                if sys.platform != "darwin":
                    raise LabError("The offline browser broker requires macOS loopback isolation.")
                command = ["/usr/bin/sandbox-exec", "-p", LOOPBACK_NETWORK, *command]
            if turn is None:
                done = subprocess.run(  # noqa: S603 - workspace-bound vetted command only
                    command,
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=BROKER_SECONDS,
                    check=False,
                )
            else:
                with turn.lock:
                    remaining = turn.remaining(deadline)
                    process = subprocess.Popen(  # noqa: S603 - workspace-bound vetted command only
                        command,
                        cwd=cwd,
                        env=environment,
                        text=True,
                        start_new_session=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    turn.active.add(process)
                with process:
                    try:
                        stdout, stderr = process.communicate(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        with turn.lock:
                            turn.failure = (
                                "An offline broker job exhausted the author turn deadline."
                            )
                            with suppress(ProcessLookupError):
                                os.killpg(process.pid, signal.SIGKILL)
                        process.communicate()
                        raise LabError(turn.failure) from None
                    finally:
                        with turn.lock:
                            turn.active.discard(process)
                done = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            result = {"code": done.returncode, "stdout": done.stdout, "stderr": done.stderr}
        except (LabError, OSError, subprocess.TimeoutExpired) as error:
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
            deadline = turn.deadline if turn else 0
            for request in sorted(folder.glob("*.request.json")):
                job = json.loads(request.read_text(encoding="utf-8"))
                request.unlink()
                threading.Thread(target=handle, args=(request, job, deadline), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return stop


def storage_environment(downloads: Path, *, offline: bool = False) -> dict[str, str]:
    if offline:
        return {
            "TUM_MCP_DATA_DIR": str(downloads.parent / "data"),
            "TUM_MCP_CONFIG_DIR": str(downloads.parent / "config"),
            "TUM_MOODLE_DATA_DIR": str(downloads.parent / "moodle"),
        }
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


def install(
    variant_dir: Path, host: str, home: Path, downloads: Path, *, offline: bool = False
) -> None:
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
    ]
    command += ["--offline"] if offline else ["--downloads", str(downloads)]
    env = (
        hosts.clean_environment(
            {"TUM_MCP_CONFIG_DIR": str(downloads.parent / "config")},
            home,
            None,
            host,
            offline=True,
        )
        if offline
        else None
    )
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
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


def restored_workspaces(history: Path, turn: int) -> frozenset[str]:
    """The app workspaces a checkpoint holds in any of its course projects."""
    listing = subprocess.run(
        ["git", f"--git-dir={history}", "ls-tree", "-r", "--name-only", f"turn-{turn}"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    found = set()
    for path in listing:
        parts = path.split("/")
        for index, part in enumerate(parts[:-2]):
            if part == "app":
                found.add(parts[index + 1])
    return frozenset(found)


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


# Run with the variant's Python: a sync under that version would write these instructions.
REFRESH = """
import sys
from pathlib import Path

from tum_mcp.course.project.store import (
    PRIVATE, agent_pointer, digest, load_state, private_path, replace_agents,
)

root = Path(sys.argv[1])
state = load_state(root)
block = agent_pointer(PRIVATE)
agents = root / "AGENTS.md"
agents.write_text(replace_agents(agents.read_text(encoding="utf-8"), block, state), "utf-8")
updated = state.model_copy(update={"agents_block_sha256": digest(block.encode())})
private_path(root, "state.json").write_text(updated.model_dump_json(indent=2), "utf-8")
"""


def refresh_instructions(python: Path, workspace: Path) -> list[str]:
    """Give each restored project the generated instructions of the variant's code; the
    course content stays as restored. Edited managed instructions stop the run, as in a sync."""
    refreshed = []
    for project in projects(workspace):
        done = subprocess.run(
            [str(python), "-I", "-c", REFRESH, str(project)], capture_output=True, text=True
        )
        if done.returncode:
            raise LabError(f"Could not refresh {project.name}'s instructions: {done.stderr[-400:]}")
        refreshed.append(project.relative_to(workspace).as_posix())
    return refreshed


def projects(workspace: Path) -> list[Path]:
    found = []
    for state in sorted(workspace.glob("**/.tum-mcp/state.json")):
        if len(state.relative_to(workspace).parts) <= 5:
            found.append(state.parent.parent)
    return found


def inventory_hash(workspace: Path, *, copy_to: Path | None = None) -> str | None:
    """Hash relative paths and bytes across every course, optionally copying those bytes."""
    inventory: dict[str, dict[str, str]] = {}
    verifiable = True
    found = projects(workspace)
    for project in found:
        files: dict[str, str] = {}
        materials = project / "materials"
        try:
            if materials.is_symlink() or not materials.is_dir():
                verifiable = False
                continue
            for folder, dirs, names in materials.walk(on_error=_inventory_error):
                for name in list(dirs):
                    if (folder / name).is_symlink():
                        dirs.remove(name)
                        verifiable = False
                for name in sorted(names):
                    source = folder / name
                    if not stat.S_ISREG(source.lstat().st_mode):
                        verifiable = False
                        continue
                    relative = source.relative_to(project).as_posix()
                    if copy_to is not None:
                        target = copy_to / source.relative_to(workspace)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, target)
                        source = target
                    with source.open("rb") as stream:
                        files[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError:
            verifiable = False
        if not files:
            verifiable = False
        inventory[project.relative_to(workspace).as_posix()] = files
    if not found or not verifiable:
        return None
    return hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()


def _inventory_error(error: OSError) -> None:
    raise error


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
    accept_drift: str | None = None,
    until: int | None = None,
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
    if scenario.offline:
        expected = ModelSpec.parse(models.DEFAULT_AUTHORS["codex"])
        if (
            author is not None
            or spec != expected
            or checkpoint
            or confirm
            or plant
            or accept_drift
            or until is not None
        ):
            raise LabError("Scored authoring uses the fixed author and complete scripted scenario.")
        if config["scenario"] != scenarios.FAI_JOURNEY or config["budget"]["judge_sessions"] != 0:
            raise LabError("Scored authoring requires a journey round with zero judges.")
        minimum_budget = FAI_SLOTS.get((variant_name, scenario.id))
        if minimum_budget is None:
            raise LabError("This variant and scenario do not name a planned authoring slot.")
        if not minimum_budget <= config["budget"]["runs"] <= 3:
            raise LabError("This slot is not covered by the recorded authoring run budget.")
    if until is not None:
        # One stage of a staged scenario: the run ends after this turn.
        scenario = dataclasses.replace(scenario, turns=scenario.turns[:until])
    variant_dir = paths.round_dir(round_id) / "variants" / variant_name
    if not (variant_dir / "variant.json").is_file():
        raise LabError(f"Variant {variant_name} does not exist; create it with `lab variant`.")
    if scenario.offline:
        manifest = json.loads((variant_dir / "variant.json").read_text(encoding="utf-8"))
        variant_spec = manifest["spec"]
        if (
            variant_spec["ref"] != config["base"]["ref"]
            or (variant_name == "base" and variant_spec["patches"])
            or any(variants.digest(Path(p["path"])) != p["sha256"] for p in variant_spec["patches"])
            or manifest.get("installed_hash") != variants.installed_hash(variant_dir)
        ):
            raise LabError("The installed variant or its recorded inputs have drifted.")
    start = 0
    source: tuple[Path, int] | None = None
    drift: dict | None = None
    if accept_drift and not checkpoint:
        raise LabError("--accept-code-drift only applies to a run resumed with --from.")
    if checkpoint:
        source = parse_checkpoint(checkpoint, round_id)
        start = source[1]
        original = json.loads((source[0].parent / "run.json").read_text(encoding="utf-8"))
        previous = paths.round_dir(original["round"]) / "variants" / original["variant"]
        changed = variants.changed_inputs(previous, variant_dir)
        refusal = scenarios.checkpoint_refusal(scenario, start, changed)
        if refusal and accept_drift:
            refusal = scenarios.drift_refusal(
                scenario, start, restored_workspaces(source[0], start)
            )
            drift = {"reason": accept_drift, "files": changed}
        if refusal:
            raise LabError(f"Checkpoint refused: {refusal}")
    if not scenario.offline:
        campus_check()
    timeout = int(config["budget"]["turn_timeout_min"]) * 60
    if scenario.offline and timeout != 12 * 60:
        raise LabError("Scored authoring requires the recorded 12-minute turn limit.")
    # A trial installs into, and clears the logs of, its host's profile, so one profile runs one
    # trial at a time; other hosts and profile slots run side by side.
    profile = paths.profile_name(spec.host)
    lock = FileLock(str(paths.state() / f"live-{profile}.lock"))
    paths.state().mkdir(parents=True, exist_ok=True)
    try:
        lock.acquire(timeout=0)
    except Timeout as error:
        raise LabError(
            f"Another live {profile} trial is running; each profile runs one at a time."
        ) from error
    try:
        if scenario.offline:
            profiles.require_offline_login()
        # Both hosts may start together; the round lock keeps the budget count and ids exact.
        with FileLock(str(paths.round_dir(round_id) / "runs.lock")):
            rounds.check_budget(round_id, "runs")
            if scenario.offline:
                claim = paths.round_dir(round_id) / f"claimed-{variant_name}-{scenario.id}"
                if claim.exists():
                    raise LabError(f"The {variant_name}/{scenario.id} slot was already claimed.")
                claim.touch(exist_ok=False)
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
            drift=drift,
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
    drift: dict | None = None,
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
    if scenario.offline:
        from skill_lab import authoring_fixture

        authoring_fixture.seed(workspace, scenario.id)
        snapshot(history, workspace, 0)
    if source:
        restore(*source, workspace)
    if source and drift is not None:
        drift["instructions_refreshed"] = refresh_instructions(python, workspace)
    if plant:
        from skill_lab import calibrate

        planted = calibrate.plant(workspace)
        (run_dir / "planted.json").write_text(json.dumps(planted, indent=2), encoding="utf-8")
    shim = bin_dir / "tum-mcp"
    broker = workspace / ".lab-broker"
    shim_env = {"SKILL_LAB_RENDER_BROKER": str(broker)}
    if scenario.offline:
        shim_env["SKILL_LAB_OFFLINE"] = "1"
    assignments = " ".join(f"{key}={shlex.quote(value)}" for key, value in shim_env.items())
    shim.write_text(
        f"#!/bin/sh\n{assignments} exec {shlex.quote(str(python))} -I "
        f'{shlex.quote(str(LAB_CODE / "shim.py"))} "$@"\n',
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
        "code_drift": drift,
        "confirm": confirm,
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "running",
        "delivery_request": scenarios.delivery_request(scenario.turns),
        "turns": [],
    }
    if scenario.offline:
        record["installed_hash"] = variants.installed_hash(variant_dir)
    write_record(run_dir, record)
    began = time.monotonic()
    storage = storage_environment(downloads, offline=scenario.offline)
    environment = hosts.clean_environment(
        storage, home, bin_dir, spec.host, offline=scenario.offline
    )
    broker_turn = (
        OfflineBrokerTurn(
            1 if scenario.id == scenarios.FAI_RESUME else 3, run_dir / "checker.jsonl"
        )
        if scenario.offline
        else None
    )
    permissions = ()
    executable = "codex"
    if scenario.offline:
        codex = shutil.which("codex", path=environment["PATH"])
        if codex is None:
            raise LabError("The isolated Codex executable is unavailable.")
        executable = str(Path(codex).resolve())
        permissions = (
            bin_dir, LAB_CODE / "shim.py", python.parent.parent,
            python.resolve().parent.parent, Path(sys.base_prefix), run_dir / "config",
            home / ".agents" / "skills", home / ".codex" / "hooks",
            Path(executable), Path("/opt/homebrew"), Path("/usr/local"),
        )  # fmt: skip
    serving = render_broker(
        broker,
        python,
        hosts.checker_command(spec, permissions=permissions, executable=executable),
        environment,
        turn=broker_turn,
    )
    try:
        if scenario.offline and installer is install:
            install(variant_dir, spec.host, home, downloads, offline=True)
        else:
            installer(variant_dir, spec.host, home, downloads)
        if source:
            snapshot(history, workspace, start)
        session = None
        for number, turn in enumerate(scenario.turns[start:], start=start + 1):
            if scenario.id == scenarios.FAI_JOURNEY and number == 3:
                authoring_fixture.release_clarification(workspace)
            entry = {"turn": number, "message": turn.say, "replies": []}
            message, attempt = turn.say, 0
            while True:
                label = f"turn-{number}" + (f"-reply-{attempt}" if attempt else "")
                clock = time.monotonic()
                if broker_turn:
                    with broker_turn.lock:
                        for pending in broker.glob("*.request.json"):
                            pending.unlink(missing_ok=True)
                        broker_turn.deadline = clock + timeout
                try:
                    result = hosts.run_turn(
                        spec,
                        message,
                        workspace=workspace,
                        environment=environment,
                        session=session,
                        timeout=timeout,
                        raw=run_dir / "raw" / f"{label}.jsonl",
                        **(
                            {"permissions": permissions, "executable": executable}
                            if permissions
                            else {}
                        ),
                    )
                finally:
                    if broker_turn:
                        broker_turn.finish()
                        for event in broker_turn.ledger_events():
                            if event["event"] == "refused":
                                broker_turn.failure = event["reason"]
                if broker_turn and broker_turn.failure:
                    result.is_error = True
                    result.error = broker_turn.failure
                if (
                    scenario.offline
                    and models.reported_matches(spec, result.model_reported) is False
                ):
                    result.is_error = True
                    result.error = "The author reported a different model."
                if (
                    scenario.offline
                    and not result.is_error
                    and (
                        not result.session_id
                        and not session
                        or result.session_id
                        and session
                        and result.session_id != session
                    )
                ):
                    result.is_error = True
                    result.error = "The author did not preserve the scripted host session."
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
        if broker_turn:
            record["checker_reservations"] = sum(
                event["event"] == "reserved" for event in broker_turn.ledger_events()
            )
            record["checker_limit"] = broker_turn.limit
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
        if scenario.offline and variants.installed_hash(variant_dir) != record["installed_hash"]:
            record["status"] = "invalid-variant"
            record["error"] = "The installed variant changed during the run."
        record["inventory_hash"] = inventory_hash(workspace)
        record["inventory_definition"] = "project-path-content-sha256-v1"
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
