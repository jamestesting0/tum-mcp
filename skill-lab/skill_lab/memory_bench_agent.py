"""Paired offline agent check (Tier C): the same model answers fixed course questions with
Course Memory disabled (arm A) and enabled (arm B) on fresh clones of a frozen corpus.

Grading is deterministic: the answer's SOURCES line against pre-registered gold, a file
hash diff for side effects, and whether the memory commands ran. No judge model is used.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from filelock import FileLock, Timeout

from skill_lab import LabError, hosts, models, paths, runs, safety, variants
from skill_lab.memory_bench import check_manifest, corpus, memory_enabled, owner
from skill_lab.models import ModelSpec

AUTHOR = "codex:gpt-6.1-terra:high"
CAP = 72
TIMEOUT = 600
PROTECTED = ("app/", "materials/", "AGENTS.md")
PROTECTED_PRIVATE = ("state.json", "coverage.json", "links.json", "knowledge.json")
CONTRACT = (
    "\n\nAnswer from the course in this folder. End your answer with one line "
    "`SOURCES: kind:key[#pages], ...` naming the course items you relied on by the keys in "
    "the course files: exercise:KEY, lesson:UNIT#BLOCK (or lesson:UNIT), concept:KEY, "
    "pattern:KEY, past:QUESTION_KEY, mock:QUESTION_KEY, lecture:LECTURE#NOTE, "
    "slides:SOURCE_KEY#PAGE or handbook:course. Write `SOURCES: none` if the course does "
    "not cover it."
)
MEMORY_CALL = re.compile(r"\bstudy\s+(context|impact)\b")

Runner = Callable[[str, Path, dict, Path], dict]


def aliases(course: Path) -> dict[str, set[str]]:
    """Every key, label and title a student-facing answer may use, mapped to item refs."""
    from tum_mcp.course.memory.store import load_inputs

    with memory_enabled():
        inputs = load_inputs(course)
    found: dict[str, set[str]] = defaultdict(set)

    def add(ref: str, *names: str | None) -> None:
        for name in names:
            if name:
                found[name.casefold().strip()].add(ref)

    for unit in inputs.study.units if inputs.study else ():
        ref = f"study/unit/{unit.key}"
        add(ref, unit.key, unit.title)
        for block in unit.blocks:
            if block.key:
                add(f"{ref}/block/{block.key}", f"{unit.key}#{block.key}", block.key, block.title)
    for group in inputs.exercises.sets if inputs.exercises else ():
        for item in group.exercises:
            add(f"exercises/set/{group.key}/exercise/{item.key}", item.key, item.label, item.title)
    if exam := inputs.exam:
        for concept in exam.concepts:
            add(f"exam/concept/{concept.key}", concept.key, concept.title)
        for pattern in exam.patterns:
            add(f"exam/pattern/{pattern.key}", pattern.key, pattern.title)
        for sitting in exam.sittings:
            for variant in sitting.variants:
                for question in variant.questions:
                    ref = (
                        f"exam/sitting/{sitting.key}/variant/{variant.key}/question/{question.key}"
                    )
                    add(ref, f"past:{question.key}", f"past:{question.number}")
        for mock in exam.mocks:
            for question in mock.questions:
                ref = f"exam/mock/{mock.key}/question/{question.key}"
                add(ref, f"mock:{question.key}", f"mock:{question.number}")
    for lecture in inputs.lectures.lectures if inputs.lectures else ():
        ref = f"lectures/lecture/{lecture.key}"
        add(ref, lecture.key, lecture.title)
        for entry in lecture.entries:
            add(f"{ref}/section/{entry.key}", f"{lecture.key}#{entry.key}", entry.key)
    for key in inputs.resources:
        add(f"source/{key}", key)
    add("handbook/course", "course", "handbook")
    return found


def cited(text: str, names: dict[str, set[str]]) -> tuple[set[str], list[str], bool]:
    """Refs named on the answer's last SOURCES line, unmatched entries, and `none`."""
    lines = [line for line in text.splitlines() if line.strip().startswith("SOURCES:")]
    if not lines:
        return set(), [], False
    body = lines[-1].split(":", 1)[1].strip().strip("`")
    if body.casefold().rstrip(".") == "none":
        return set(), [], True
    refs, unmatched = set(), []
    for entry in filter(None, (part.strip().strip("`") for part in body.split(","))):
        kind, _, rest = entry.partition(":")
        key = rest.split("#pages")[0] if kind in {"past", "mock"} else rest
        candidates = [f"{kind}:{key}"] if kind in {"past", "mock"} else [key]
        if kind == "slides":
            candidates = [key.split("#")[0]]
        elif "#" in key:
            candidates.append(key.split("#")[-1])
        match = next((names[c.casefold()] for c in candidates if c.casefold() in names), None)
        if match:
            refs |= match
        else:
            unmatched.append(entry)
    return refs, unmatched, False


def grade(task: dict, text: str, names: dict[str, set[str]]) -> dict:
    refs, unmatched, none = cited(text, names)
    if task.get("none"):
        return {"success": none, "recall": 1.0 if none else 0.0, "unmatched": unmatched}
    if task.get("text_contains"):
        ok = all(fragment in text for fragment in task["text_contains"])
        return {"success": ok, "recall": 1.0 if ok else 0.0, "unmatched": unmatched}
    owners = {owner(ref) for ref in refs} if task.get("owner_level") else set()
    required = task["required"]
    hit = [ref for ref in required if ref in refs or ref in owners]
    forbidden = sorted(set(task.get("forbidden", [])) & refs)
    return {
        "success": len(hit) == len(required) and not forbidden,
        "recall": round(len(hit) / len(required), 3),
        "forbidden": forbidden,
        "unmatched": unmatched,
    }


LEARNER_WRITE = re.compile(r"\bstudy\s+learner\s+(note|mistake|resolve|plan)\b")
MANAGED = re.compile(r"<!-- tum-mcp:study:start -->.*?<!-- tum-mcp:study:end -->", re.S)


def managed_block(variant_dir: Path) -> str:
    """The course instructions of the build under test; a frozen course keeps the block
    written at freeze time until a sync refreshes it, so each episode refreshes it here."""
    script = (
        "from tum_mcp.course.project.store import PRIVATE, agent_pointer;"
        "print(agent_pointer(PRIVATE), end='')"
    )
    if not variants.python_of(variant_dir).is_file():
        return "<!-- tum-mcp:study:start -->test<!-- tum-mcp:study:end -->"
    done = subprocess.run(
        [str(variants.python_of(variant_dir)), "-I", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def seed(shim: Path, workspace: Path, environment: dict, steps: list, *, on: bool) -> None:
    """Write a task's synthetic learner record through the product CLI before the episode."""
    last = ""

    def cli(*args: str) -> dict:
        done = subprocess.run(
            [str(shim), "study", "learner", *args],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode:
            raise LabError(f"Seeding {args[:2]} failed: {done.stderr.strip()[-300:]}")
        return json.loads(done.stdout)

    for step in steps:
        match step:
            case ["init", state]:
                if on and state == "on":
                    cli("enable", ".")
            case ["mistake", item, note, source]:
                last = cli("mistake", ".", "--item", item, "--note", note, "--source", source)["id"]
            case ["resolve-last"]:
                cli("resolve", ".", last)
            case ["note", item, outcome, note, *offset]:
                when = time.time() + 86400 * (offset[0] if offset else 0)
                day = time.strftime("%Y-%m-%d", time.localtime(when))
                cli("note", ".", "--item", item, "--outcome", outcome, "--note", note, "--on", day)
            case unknown:
                raise LabError(f"Unknown learner setup step {unknown}.")


def learner_state(workspace: Path, agents_before: str) -> dict:
    path = workspace / ".tum-mcp" / "learner" / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []
    after = (workspace / "AGENTS.md").read_text()
    added = [line for line in after.splitlines() if line not in agents_before.splitlines()]
    heading = after.split("## Preferences", 1)
    return {
        "events": rows,
        "events_file": path.is_file(),
        "managed_changed": MANAGED.findall(after) != MANAGED.findall(agents_before),
        "preferences_added": len(heading) == 2
        and any(line in heading[1] for line in added if line.strip()),
    }


def final_value(text: str, key: str) -> str | None:
    lines = [line for line in text.splitlines() if line.strip().upper().startswith(key + ":")]
    return lines[-1].split(":", 1)[1].strip().strip("`*. ").casefold() if lines else None


def grade_learner(task: dict, row: dict, names: dict[str, set[str]]) -> dict:
    checks, calls, answer = task.get("checks", {}), row.get("calls", []), row.get("answer", "")
    events = row.get("events", [])
    failed = []
    for needle in checks.get("no_calls", []):
        if any(needle in call for call in calls):
            failed.append(f"called {needle}")
    for needle, (low, high) in checks.get("calls", {}).items():
        count = sum(needle in call for call in calls)
        if not low <= count <= high:
            failed.append(f"{needle} x{count}")
    writes = sum(bool(LEARNER_WRITE.search(call)) for call in calls)
    if writes > checks.get("max_writes", 99):
        failed.append(f"{writes} writes")
    expect = checks.get("events", {})
    if "count" in expect and len(events) != expect["count"]:
        failed.append(f"{len(events)} events")
    if expect.get("count") == 0 and row.get("events_file"):
        failed.append("events file")
    if "item" in expect:
        found = [
            e for e in events if e.get("item") == expect["item"] and e["kind"] in expect["kinds"]
        ]
        if len(found) < expect["min"]:
            failed.append("no matching event")
    if "absent_prefix" in expect and any(
        (e.get("item") or "").startswith(expect["absent_prefix"]) for e in events
    ):
        failed.append("forgotten item remains")
    for item in expect.get("present", []):
        if not any(e.get("item") == item for e in events):
            failed.append(f"{item} lost")
    for key, value in checks.get("final_line", {}).items():
        got = final_value(answer, key)
        word = got.split()[0].strip(".,") if got else ""
        if got is None or (word not in {"none", ""} if value == "none" else word != value):
            failed.append(f"{key}={got}")
    for text in checks.get("absent_text", []):
        if text.casefold() in answer.casefold():
            failed.append(f"mentioned {text}")
    if size := checks.get("no_overlap_words"):
        words = re.findall(r"\w+", task["prompt"].casefold())
        spans = {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}
        stored = " ".join(re.findall(r"\w+", json.dumps(events).casefold()))
        if any(span in stored for span in spans):
            failed.append("copied chat text")
    if checks.get("preferences_line") and not row.get("preferences_added"):
        failed.append("no preference line")
    if row.get("managed_changed"):
        failed.append("managed block edited")
    if "required_any" in task:
        refs, _, _ = cited(answer, names)
        failed += [f"missing {group[0]}" for group in task["required_any"] if not refs & set(group)]
        failed += [f"recommended {ref}" for ref in task.get("forbidden", []) if ref in refs]
    return {"success": not failed, "recall": 0.0 if failed else 1.0, "failed": failed}


def tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def protected_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    return sorted(
        name
        for name in changed
        if name.startswith(PROTECTED)
        or any(name == f".tum-mcp/{private}" for private in PROTECTED_PRIVATE)
    )


def worktree_variant() -> Path:
    """Build (once) a lab variant from the working tree, named by its product sources."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "src/tum_mcp"],
        cwd=paths.REPO,
        capture_output=True,
        check=True,
    ).stdout
    hasher = hashlib.sha256()
    for relative in sorted(filter(None, listed.decode().split("\0"))):
        source = paths.REPO / relative
        if source.is_file():
            hasher.update(relative.encode() + b"\0" + source.read_bytes())
    name = f"worktree-{hasher.hexdigest()[:12]}"
    return variants.create("memory-bench", name, variants.Base(variants.WORKTREE))


def codex_runner(spec: ModelSpec, variant_dir: Path, home: Path, bin_dir: Path) -> Runner:
    def run(message: str, workspace: Path, environment: dict, raw: Path) -> dict:
        command = hosts.codex_command(spec, message, workspace, session=None)
        command[-1:-1] = ["-c", "mcp_servers={}"]
        clock = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                check=False,
            )
            output, failure = completed.stdout, ""
        except subprocess.TimeoutExpired as expired:
            output = expired.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", "replace")
            failure = f"timed out after {TIMEOUT}s"
        raw.write_text(output, encoding="utf-8")
        events = hosts.parse_lines(output)
        result = hosts.parse_codex(events, home)
        commands = [
            str((event.get("item") or {}).get("command", ""))
            for event in events
            if event.get("type") == "item.completed"
            and (event.get("item") or {}).get("type") == "command_execution"
        ]
        return {
            "text": result.text,
            "error": failure or (result.error if result.is_error else ""),
            "usage": result.usage,
            "model_reported": result.model_reported,
            "seconds": round(time.monotonic() - clock, 1),
            "commands": len(commands),
            "memory_calls": sum(bool(MEMORY_CALL.search(c)) for c in commands),
            "calls": [c[-300:] for c in commands],
        }

    return run


def install_arm(variant_dir: Path, home: Path, config: Path, data: Path) -> list[str]:
    environment = {
        **hosts.clean_environment({}, home, None, "codex"),
        "HOME": str(Path.home()),
        "TUM_MCP_CONFIG_DIR": str(config),
        "TUM_MCP_DATA_DIR": str(data),
    }
    result = subprocess.run(
        [
            str(variants.python_of(variant_dir)),
            "-I",
            str(runs.LAB_CODE / "install_variant.py"),
            "--host",
            "codex",
            "--home",
            str(home),
            "--proxy",
            str(runs.LAB_CODE / "mcp_proxy.py"),
            "--block",
            ",".join(sorted(safety.BLOCKED_TOOLS)),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise LabError(f"Installing the arm failed: {result.stderr.strip()[-600:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])["skills"]


def episodes(output: Path) -> list[dict]:
    path = output / "episodes.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def disagreeing(rows: list[dict]) -> list[str]:
    outcome: dict[str, dict[str, set[bool]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        outcome[row["task"]][row["arm"]].add(row["success"])
    return sorted(
        task for task, arms in outcome.items() if len(arms) == 2 and arms["A"] != arms["B"]
    )


def plan_stage(
    rows: list[dict],
    tasks: list[dict],
    stage: int,
    arms: tuple[str, ...] = ("A", "B"),
    trials: int = 3,
) -> list[tuple[str, str, int]]:
    """Stage 1: one trial per task; 2: trials 2-3 where arms disagreed; 3: trials 1-3 for all."""
    done = {(row["task"], row["arm"], row["trial"]) for row in rows}
    match stage:
        case 1:
            wanted = [(task["id"], arm, 1) for arm in arms for task in tasks]
        case 2:
            wanted = [
                (task, arm, trial)
                for arm in arms
                for task in disagreeing([r for r in rows if r["trial"] == 1])
                for trial in (2, 3)
            ]
        case 3:
            wanted = [
                (task["id"], arm, trial)
                for arm in arms
                for task in tasks
                for trial in range(1, task.get("trials", trials) + 1)
            ]
        case unreachable:
            raise LabError(f"Unknown stage {unreachable}.")
    pending = [item for item in wanted if item not in done]
    if len(rows) + len(pending) > CAP:
        raise LabError(f"Stage {stage} would exceed the {CAP}-episode cap.")
    return pending


def run_stage(
    name: str,
    label: str,
    stage: int,
    *,
    arms: tuple[str, ...] = ("A", "B"),
    tasks_file: str = "agent-tasks.json",
    author: str = AUTHOR,
    trials: int = 3,
    runner_factory: Callable[[Path, Path, Path], Runner] | None = None,
    installer: Callable[[Path, Path, Path, Path], list[str]] = install_arm,
) -> dict:
    course = check_manifest(name)
    tasks = json.loads((corpus(name) / tasks_file).read_text())
    output = corpus(name) / "agent" / label
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir(exist_ok=True)
    rows = episodes(output)
    pending = plan_stage(rows, tasks, stage, arms, trials)
    if not pending:
        return report(name, label)
    spec = ModelSpec.parse(author)
    home = paths.profile_home("codex")
    if runner_factory is None:
        models.validate(spec, role="author", profile_home=home)
        variant_dir = worktree_variant()

        def runner_factory(bin_dir: Path, _home: Path, _variant: Path) -> Runner:
            return codex_runner(spec, variant_dir, home, bin_dir)

    else:
        variant_dir = paths.state() / "fake-variant"
    identity = {
        "author": author,
        "variant": variant_dir.name,
        "manifest": hashlib.sha256((corpus(name) / "manifest.json").read_bytes()).hexdigest(),
        # What the agent sees; gold corrections regrade stored answers and keep the identity.
        "prompts": hashlib.sha256(
            json.dumps([[task["id"], task["prompt"]] for task in tasks]).encode()
        ).hexdigest(),
    } | ({"tasks": tasks_file} if tasks_file != "agent-tasks.json" else {})
    known = output / "identity.json"
    if known.is_file() and json.loads(known.read_text()) != identity:
        raise LabError("This label was run with another variant, corpus or task set.")
    known.write_text(json.dumps(identity, indent=1))
    names = aliases(course)
    lock = FileLock(str(paths.state() / "live-codex.lock"))
    paths.state().mkdir(parents=True, exist_ok=True)
    try:
        lock.acquire(timeout=0)
    except Timeout as error:
        raise LabError(
            "Another live codex trial is running; each host runs one at a time."
        ) from error
    try:
        with tempfile.TemporaryDirectory(prefix="memory-bench-agent-") as folder:
            scratch = Path(folder)
            bin_dir = scratch / "bin"
            bin_dir.mkdir()
            shim = bin_dir / "tum-mcp"
            shim.write_text(
                f'#!/bin/sh\nexec "{variants.python_of(variant_dir)}" -I '
                f'"{runs.LAB_CODE / "shim.py"}" "$@"\n'
            )
            shim.chmod(0o755)
            runner = runner_factory(bin_dir, home, variant_dir)
            block = managed_block(variant_dir)
            for arm in ("A", "B", "L", "O"):
                todo = [item for item in pending if item[1] == arm]
                if not todo:
                    continue
                config, data = scratch / arm / "config", scratch / arm / "data"
                config.mkdir(parents=True)
                data.mkdir(parents=True)
                memory = arm != "A"
                selection = {"schema_version": 1} | ({"course_memory": True} if memory else {})
                (config / "extensions.json").write_text(json.dumps(selection))
                skills = installer(variant_dir, home, config, data)
                if ("course-memory" in skills) != memory:
                    raise LabError(f"Arm {arm} installed the wrong skills: {skills}.")
                environment = hosts.clean_environment(
                    {"TUM_MCP_CONFIG_DIR": str(config), "TUM_MCP_DATA_DIR": str(data)},
                    home,
                    bin_dir,
                    "codex",
                )
                for task_id, _, trial in todo:
                    task = next(t for t in tasks if t["id"] == task_id)
                    workspace = (
                        paths.workspaces() / "memory-bench" / f"{label}-{task_id}-{arm}-{trial}"
                    )
                    shutil.rmtree(workspace, ignore_errors=True)
                    workspace.parent.mkdir(parents=True, exist_ok=True)
                    subprocess.run(["cp", "-cR", str(course), str(workspace)], check=True)
                    agents = workspace / "AGENTS.md"
                    agents.write_text(MANAGED.sub(lambda _: block, agents.read_text(), count=1))
                    learner = "setup" in task
                    if learner:
                        seed(shim, workspace, environment, task["setup"], on=arm != "O")
                    before = tree(workspace)
                    agents_before = (workspace / "AGENTS.md").read_text()
                    raw = output / "raw" / f"{task_id}-{arm}-{trial}.jsonl"
                    contract = CONTRACT if not learner or "required_any" in task else ""
                    result = runner(task["prompt"] + contract, workspace, environment, raw)
                    changes = protected_changes(before, tree(workspace))
                    if learner:
                        result |= learner_state(workspace, agents_before)
                        changes = [c for c in changes if c != "AGENTS.md"] + (
                            ["AGENTS.md#managed"] if result["managed_changed"] else []
                        )
                    graded = (
                        grade_learner(task, result | {"answer": result["text"]}, names)
                        if learner
                        else grade(task, result["text"], names)
                    )
                    row = {
                        "task": task_id,
                        "kind": task["kind"],
                        "arm": arm,
                        "trial": trial,
                        **graded,
                        "protected_writes": changes,
                        "over_trigger": task["kind"] == "control" and result["memory_calls"] > 0,
                        **{k: v for k, v in result.items() if k != "text"},
                        "answer": result["text"][-1500:],
                    }
                    with (output / "episodes.jsonl").open("a") as stream:
                        stream.write(json.dumps(row) + "\n")
                    shutil.rmtree(workspace, ignore_errors=True)
                    runs.clear_host_logs(home, "codex")
    finally:
        lock.release()
    hits = safety.scan_tree(output)
    if hits:
        raise LabError(f"Credential-like text in agent results: {hits[:3]}")
    return report(name, label)


def graded(name: str, label: str) -> list[dict]:
    known = corpus(name) / "agent" / label / "identity.json"
    tasks_file = json.loads(known.read_text()).get("tasks", "agent-tasks.json")
    tasks = {task["id"]: task for task in json.loads((corpus(name) / tasks_file).read_text())}
    names = aliases(check_manifest(name))
    # Grade from the stored answers with the current gold, so a gold correction never
    # needs a rerun; every arm is regraded alike.
    rows = episodes(corpus(name) / "agent" / label)
    return [
        row
        | (
            grade_learner(tasks[row["task"]], row, names)
            if "setup" in tasks[row["task"]]
            else grade(tasks[row["task"]], row["answer"], names)
        )
        for row in rows
    ]


def usage(row: dict, field: str) -> int:
    return int((row.get("usage") or {}).get(field, 0))


# Cost is what the provider bills at full rate: uncached input plus output. Cached input is
# reported separately because it is billed at a fraction and dominates the raw input count.
METRICS: dict[str, Callable[[dict], float]] = {
    "cost": lambda r: (
        usage(r, "input_tokens") - usage(r, "cached_input_tokens") + usage(r, "output_tokens")
    ),
    "seconds": lambda r: float(r["seconds"]),
    "requests": lambda r: float(r["commands"] or 1),
    "cached_input": lambda r: float(usage(r, "cached_input_tokens")),
}


def median(values: list[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def bootstrap(values: list[float]) -> tuple[float, float] | None:
    """A deterministic 95% interval for the median over tasks."""
    if not values:
        return None

    def draw(sample: int, slot: int) -> float:
        seed = hashlib.sha256(f"{sample}:{slot}".encode()).digest()
        return values[int.from_bytes(seed[:4]) % len(values)]

    medians = sorted(
        median([draw(sample, slot) for slot in range(len(values))]) for sample in range(2000)
    )
    return medians[int(0.025 * len(medians))], medians[int(0.975 * len(medians))]


def summarize(rows: list[dict], pairs: tuple[tuple[str, str], ...]) -> dict:
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    kinds: dict[str, str] = {}
    for row in rows:
        by[(row["task"], row["arm"])].append(row)
        kinds[row["task"]] = row["kind"]
    arms = sorted({row["arm"] for row in rows})
    tasks = sorted(kinds)

    def mean(task: str, arm: str, metric: Callable[[dict], float]) -> float:
        found = by[(task, arm)]
        return sum(metric(r) for r in found) / len(found)

    success = {
        kind: {
            arm: sum(
                mean(t, arm, lambda r: float(r["success"])) > 0.5 for t in tasks if kinds[t] == kind
            )
            for arm in arms
        }
        | {"tasks": sum(kinds[t] == kind for t in tasks)}
        for kind in ("relational", "control")
    }
    ratios = {}
    for left, right in pairs:
        for name, metric in METRICS.items():
            per_task = {
                t: mean(t, left, metric) / mean(t, right, metric)
                for t in tasks
                if by[(t, left)] and by[(t, right)] and mean(t, right, metric)
            }
            values = list(per_task.values())
            # The change under test rarely touches control tasks, so a control ratio far
            # from 1.0 shows drift between the batches being compared.
            controls = [v for t, v in per_task.items() if kinds[t] == "control"]
            ratios[f"{left}/{right} {name}"] = {
                "median": median(values),
                "interval": bootstrap(values),
                "tasks": len(values),
                "controls": median(controls),
            }
    return {
        "episodes": {arm: sum(len(by[(t, arm)]) for t in tasks) for arm in arms},
        "trials_per_task": {arm: sorted({len(by[(t, arm)]) for t in tasks}) for arm in arms},
        "success": success,
        "per_task_success": {
            t: {
                arm: round(mean(t, arm, lambda r: float(r["success"])), 2)
                for arm in arms
                if by[(t, arm)]
            }
            for t in tasks
        },
        "totals": {
            arm: {
                name: round(sum(metric(r) for r in rows if r["arm"] == arm))
                for name, metric in METRICS.items()
            }
            for arm in arms
        },
        "ratios": ratios,
        "memory_calls": {
            arm: {
                kind: sum(r["memory_calls"] for r in rows if r["arm"] == arm and r["kind"] == kind)
                for kind in ("relational", "control")
            }
            for arm in arms
        },
        "protected_writes": [
            (r["task"], r["arm"], r["protected_writes"]) for r in rows if r["protected_writes"]
        ],
        "errors": [(r["task"], r["arm"], r["error"][:120]) for r in rows if r.get("error")],
        "models_reported": sorted({r["model_reported"] for r in rows if r.get("model_reported")}),
    }


def improved(summary: dict, pair: str, threshold: float) -> bool:
    return any(
        (entry := summary["ratios"].get(f"{pair} {metric}"))
        and entry["median"] is not None
        and entry["median"] <= threshold
        and entry["interval"][1] < 1.0
        for metric in ("cost", "seconds")
    )


def accurate(summary: dict, arm: str, *others: str) -> bool:
    return not summary["protected_writes"] and all(
        summary["success"][kind][arm] >= summary["success"][kind][other]
        for kind in ("relational", "control")
        for other in others
        if other in summary["success"][kind]
    )


def report(name: str, label: str) -> dict:
    output = corpus(name) / "agent" / label
    rows = graded(name, label)
    paired = {row["arm"] for row in rows} == {"A", "B"}
    summary = summarize(rows, (("B", "A"),) if paired else ())
    summary["decision"] = (
        {
            "non_inferior": accurate(summary, "B", "A"),
            "benefit": accurate(summary, "B", "A") and improved(summary, "B/A", 0.75),
        }
        if paired
        else {"single_arm": "compare against a paired label with agent-compare"}
    )
    (output / "report.json").write_text(json.dumps(summary, indent=1))
    (output / "report.md").write_text(render(summary, "Course Memory paired agent check"))
    return summary


def compare(name: str, base: str, label: str) -> dict:
    """Arms A and B from the stored base label against the candidate (arm B of label) as C."""
    rows = graded(name, base) + [
        row | {"arm": "C"} for row in graded(name, label) if row["arm"] == "B"
    ]
    summary = summarize(rows, (("C", "B"), ("C", "A"), ("B", "A")))
    cost = summary["ratios"].get("C/B cost", {}).get("median")
    summary["decision"] = {
        "keep_candidate": accurate(summary, "C", "A", "B") and improved(summary, "C/B", 0.90),
        "candidate_non_inferior": accurate(summary, "C", "A", "B")
        and cost is not None
        and cost <= 1.0,
        "memory_beats_off": accurate(summary, "C", "A") and improved(summary, "C/A", 0.90),
    }
    output = corpus(name) / "agent" / f"compare-{base}-{label}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "compare.json").write_text(json.dumps(summary, indent=1))
    (output / "compare.md").write_text(render(summary, f"Course Memory: {label} against {base}"))
    return summary


def render(summary: dict, title: str) -> str:
    arms = sorted(summary["episodes"])
    header = " | ".join(arms)
    lines = [
        f"# {title}",
        "",
        f"Model {AUTHOR}; episodes {summary['episodes']}; trials per task "
        f"{summary['trials_per_task']}; reported models: "
        f"{', '.join(summary['models_reported']) or 'none'}.",
        "",
        f"| Tasks solved (majority) | {header} |",
        "| --- |" + " --- |" * len(arms),
        *(
            f"| {kind} | " + " | ".join(f"{row[arm]}/{row['tasks']}" for arm in arms) + " |"
            for kind, row in summary["success"].items()
        ),
        "",
        f"| Totals | {header} |",
        "| --- |" + " --- |" * len(arms),
        *(
            f"| {metric} | "
            + " | ".join(str(summary["totals"][arm][metric]) for arm in arms)
            + " |"
            for metric in METRICS
        ),
        "",
        "| Paired ratio (per-task means) | Median | 95% interval | Tasks | Controls median |",
        "| --- | --- | --- | --- | --- |",
        *(
            f"| {name} | {round(v['median'], 3) if v['median'] is not None else None} | "
            f"{tuple(round(x, 3) for x in v['interval']) if v['interval'] else None} | "
            f"{v['tasks']} | {round(v['controls'], 3) if v.get('controls') is not None else None} |"
            for name, v in summary["ratios"].items()
        ),
        "",
        f"Memory calls by arm and task kind: {summary['memory_calls']}.",
        f"Protected writes: {summary['protected_writes'] or 'none'}. "
        f"Errors: {summary['errors'] or 'none'}.",
        "",
        "## Pre-registered decision",
        "",
        *(f"- {key}: **{value}**" for key, value in summary["decision"].items()),
        "",
        "Cost is uncached input plus output tokens. With 12 tasks only large effects are "
        "detectable; results hold for this model and course.",
    ]
    return "\n".join(lines) + "\n"
