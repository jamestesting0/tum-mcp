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


def plan_stage(rows: list[dict], tasks: list[dict], stage: int) -> list[tuple[str, str, int]]:
    done = {(row["task"], row["arm"], row["trial"]) for row in rows}
    if stage == 1:
        wanted = [(task["id"], arm, 1) for arm in ("A", "B") for task in tasks]
    else:
        wanted = [
            (task, arm, trial)
            for arm in ("A", "B")
            for task in disagreeing([r for r in rows if r["trial"] == 1])
            for trial in (2, 3)
        ]
    pending = [item for item in wanted if item not in done]
    if len(rows) + len(pending) > CAP:
        raise LabError(f"Stage {stage} would exceed the {CAP}-episode cap.")
    return pending


def run_stage(
    name: str,
    label: str,
    stage: int,
    *,
    runner_factory: Callable[[Path, Path, Path], Runner] | None = None,
    installer: Callable[[Path, Path, Path, Path], list[str]] = install_arm,
) -> dict:
    course = check_manifest(name)
    tasks = json.loads((corpus(name) / "agent-tasks.json").read_text())
    output = corpus(name) / "agent" / label
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir(exist_ok=True)
    rows = episodes(output)
    pending = plan_stage(rows, tasks, stage)
    if not pending:
        return report(name, label)
    spec = ModelSpec.parse(AUTHOR)
    home = paths.profile_home("codex")
    if runner_factory is None:
        models.validate(spec, role="author", profile_home=home)
        variant_dir = worktree_variant()

        def runner_factory(bin_dir: Path, _home: Path, _variant: Path) -> Runner:
            return codex_runner(spec, variant_dir, home, bin_dir)

    else:
        variant_dir = paths.state() / "fake-variant"
    identity = {
        "author": AUTHOR,
        "variant": variant_dir.name,
        "manifest": hashlib.sha256((corpus(name) / "manifest.json").read_bytes()).hexdigest(),
        "tasks": hashlib.sha256((corpus(name) / "agent-tasks.json").read_bytes()).hexdigest(),
    }
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
            for arm in ("A", "B"):
                todo = [item for item in pending if item[1] == arm]
                if not todo:
                    continue
                config, data = scratch / arm / "config", scratch / arm / "data"
                config.mkdir(parents=True)
                data.mkdir(parents=True)
                selection = {"schema_version": 1} | ({"course_memory": True} if arm == "B" else {})
                (config / "extensions.json").write_text(json.dumps(selection))
                skills = installer(variant_dir, home, config, data)
                if ("course-memory" in skills) != (arm == "B"):
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
                    before = tree(workspace)
                    raw = output / "raw" / f"{task_id}-{arm}-{trial}.jsonl"
                    result = runner(task["prompt"] + CONTRACT, workspace, environment, raw)
                    changes = protected_changes(before, tree(workspace))
                    graded = grade(task, result["text"], names)
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


def report(name: str, label: str) -> dict:
    output = corpus(name) / "agent" / label
    tasks = {
        task["id"]: task for task in json.loads((corpus(name) / "agent-tasks.json").read_text())
    }
    names = aliases(check_manifest(name))
    # Grade from the stored answers with the current gold, so a gold correction never
    # needs a rerun; every arm is regraded alike.
    rows = [row | grade(tasks[row["task"]], row["answer"], names) for row in episodes(output)]
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by[(row["task"], row["arm"])].append(row)
    tasks = sorted({row["task"] for row in rows})

    def rate(task: str, arm: str) -> float | None:
        found = by.get((task, arm), [])
        return sum(r["success"] for r in found) / len(found) if found else None

    def majority(task: str, arm: str) -> bool:
        value = rate(task, arm)
        return value is not None and value > 0.5

    relational = [t for t in tasks if by[(t, "A")] and by[(t, "A")][0]["kind"] == "relational"]
    controls = [t for t in tasks if t not in relational]

    def tokens(row: dict) -> int:
        usage = row.get("usage") or {}
        return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))

    ratios = defaultdict(list)
    for task in tasks:
        a, b = by.get((task, "A"), []), by.get((task, "B"), [])
        if not a or not b:
            continue
        for metric, value in (("tokens", tokens), ("requests", lambda r: r["commands"] or 1)):
            mean_a = sum(value(r) for r in a) / len(a)
            mean_b = sum(value(r) for r in b) / len(b)
            if mean_a:
                ratios[metric].append(mean_b / mean_a)

    def median(values: list[float]) -> float | None:
        ordered = sorted(values)
        return ordered[len(ordered) // 2] if ordered else None

    def bootstrap_upper(values: list[float]) -> float | None:
        if not values:
            return None

        def draw(sample: int, slot: int) -> float:
            seed = hashlib.sha256(f"{sample}:{slot}".encode()).digest()
            return values[int.from_bytes(seed[:4]) % len(values)]

        medians = sorted(
            median([draw(sample, slot) for slot in range(len(values))]) for sample in range(2000)
        )
        return medians[int(0.975 * len(medians))]

    rel_a = sum(majority(t, "A") for t in relational)
    rel_b = sum(majority(t, "B") for t in relational)
    ctl_a = sum(majority(t, "A") for t in controls)
    ctl_b = sum(majority(t, "B") for t in controls)
    writes = [row for row in rows if row["protected_writes"]]
    errors = [row for row in rows if row.get("error")]
    summary = {
        "episodes": len(rows),
        "relational_success": {"A": rel_a, "B": rel_b, "tasks": len(relational)},
        "control_success": {"A": ctl_a, "B": ctl_b, "tasks": len(controls)},
        "over_trigger_episodes": sum(row["over_trigger"] for row in rows),
        "memory_calls_on_relational_B": sum(
            row["memory_calls"] for row in rows if row["arm"] == "B" and row["kind"] == "relational"
        ),
        "protected_writes": [(r["task"], r["arm"], r["protected_writes"]) for r in writes],
        "errors": [(r["task"], r["arm"], r["error"][:120]) for r in errors],
        "median_ratio_B_over_A": {k: median(v) for k, v in ratios.items()},
        "bootstrap_upper_95": {k: bootstrap_upper(v) for k, v in ratios.items()},
        "per_task": {task: {"A": rate(task, "A"), "B": rate(task, "B")} for task in tasks},
        "models_reported": sorted({r["model_reported"] for r in rows if r.get("model_reported")}),
    }
    non_inferior = rel_b >= rel_a and ctl_b >= ctl_a and not writes
    efficiency = any(
        (summary["median_ratio_B_over_A"].get(m) or 2) <= 0.75
        and (summary["bootstrap_upper_95"].get(m) or 2) < 1.0
        for m in ("tokens", "requests")
    )
    summary["decision"] = {
        "non_inferior": non_inferior,
        "benefit": non_inferior and (rel_b >= rel_a + 2 or efficiency),
    }
    (output / "report.json").write_text(json.dumps(summary, indent=1))
    (output / "report.md").write_text(render(summary))
    return summary


def render(summary: dict) -> str:
    rel, ctl = summary["relational_success"], summary["control_success"]
    ratio, upper = summary["median_ratio_B_over_A"], summary["bootstrap_upper_95"]
    lines = [
        "# Course Memory paired agent check",
        "",
        f"Model {AUTHOR}; {summary['episodes']} episodes; reported models: "
        f"{', '.join(summary['models_reported']) or 'none'}.",
        "",
        "| Measure | Arm A (memory off) | Arm B (memory on) |",
        "| --- | --- | --- |",
        *(
            f"| {label} tasks solved (majority) | {row['A']}/{row['tasks']} "
            f"| {row['B']}/{row['tasks']} |"
            for label, row in (("Relational", rel), ("Control", ctl))
        ),
        "",
        "| Paired ratio B/A | Median | Bootstrap 95% upper |",
        "| --- | --- | --- |",
        *(f"| {k} | {ratio.get(k)} | {upper.get(k)} |" for k in ("tokens", "requests")),
        "",
        f"Memory calls on relational tasks (arm B): {summary['memory_calls_on_relational_B']}; "
        f"memory calls on control tasks: {summary['over_trigger_episodes']}.",
        f"Protected writes: {summary['protected_writes'] or 'none'}. "
        f"Errors: {summary['errors'] or 'none'}.",
        "",
        "| Task | A success rate | B success rate |",
        "| --- | --- | --- |",
        *(f"| {task} | {v['A']} | {v['B']} |" for task, v in summary["per_task"].items()),
        "",
        "## Pre-registered decision",
        "",
        f"- Non-inferior (B relational and control successes >= A, no protected writes): "
        f"**{summary['decision']['non_inferior']}**",
        f"- Benefit (non-inferior and +2 relational tasks, or median token or request ratio "
        f"<= 0.75 with bootstrap upper < 1.0): **{summary['decision']['benefit']}**",
        "",
        "With this few tasks only large effects are detectable; the result holds for this model.",
    ]
    return "\n".join(lines) + "\n"
