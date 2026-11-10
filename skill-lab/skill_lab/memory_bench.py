"""Deterministic Course Memory benchmark (Tier B) over frozen copies of real courses.

Gold comes from the course's own authored links and citations, read from the native
workspace models. Every packet a run produces is stored, so metrics are recomputed from
stored packets and a baseline is never rerun. Nothing here calls a model or the campus.
"""

import hashlib
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skill_lab import LabError, paths

TEACHING = {"limit": 4, "max_bytes": 8000}
DEFAULT = {"limit": 12, "max_bytes": 24000}
IMPACT = {"limit": 30, "max_bytes": 65536}
WORKSPACES = ("study", "exercises", "exam", "lectures")


def root() -> Path:
    return paths.state() / "benchmarks" / "course-memory"


def corpus(name: str) -> Path:
    return root() / name


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def memory_enabled() -> Iterator[None]:
    """Enable Course Memory in a throwaway config; the user's selection is never touched."""
    saved = {key: os.environ.get(key) for key in ("TUM_MCP_CONFIG_DIR", "TUM_MCP_DATA_DIR")}
    with tempfile.TemporaryDirectory(prefix="memory-bench-") as folder:
        config = Path(folder) / "config"
        config.mkdir()
        (config / "extensions.json").write_text('{"schema_version":1,"course_memory":true}')
        os.environ["TUM_MCP_CONFIG_DIR"] = str(config)
        os.environ["TUM_MCP_DATA_DIR"] = str(Path(folder) / "data")
        try:
            yield
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def owner(ref: str) -> str:
    parts = ref.split("/")
    size = {"study": 3, "exercises": 5, "lectures": 3}.get(parts[0])
    if parts[0] == "exam":
        size = 5 if parts[1] == "sitting" else 3
    return "/".join(parts[:size])


def workspace(ref: str) -> str:
    return ref.split("/", 1)[0]


def links(inputs) -> list[tuple[str, str, str]]:
    """Every authored cross-item link as (family, from, to) typed refs."""
    found: list[tuple[str, str, str]] = []
    study, exercises, exam, lectures = (
        inputs.study,
        inputs.exercises,
        inputs.exam,
        inputs.lectures,
    )

    def passage(unit: str, block: str | None) -> str:
        return f"study/unit/{unit}" + (f"/block/{block}" if block else "")

    exercise_ref = {
        item.key: f"exercises/set/{group.key}/exercise/{item.key}"
        for group in (exercises.sets if exercises else ())
        for item in group.exercises
    }
    for unit in study.units if study else ():
        for key in unit.lectures:
            found.append(("unit.lectures", f"study/unit/{unit.key}", f"lectures/lecture/{key}"))
    for group in exercises.sets if exercises else ():
        for item in group.exercises:
            ref = exercise_ref[item.key]
            for need in item.prerequisites:
                found.append(("exercise.prerequisites", ref, passage(need.unit, need.block)))
            for key in item.distilled_from:
                found.append(("exercise.distilled_from", ref, exercise_ref[key]))
    if exam:
        past = {
            question.key: f"exam/sitting/{s.key}/variant/{v.key}/question/{question.key}"
            for s in exam.sittings
            for v in s.variants
            for question in v.questions
        }
        for concept in exam.concepts:
            ref = f"exam/concept/{concept.key}"
            for key in concept.units:
                found.append(("concept.units", ref, f"study/unit/{key}"))
            for item in concept.passages:
                found.append(("concept.passages", ref, passage(item.unit, item.block)))
            for item in concept.exercises:
                found.append(("concept.exercises", ref, exercise_ref[item.exercise]))
            if concept.workflow_from:
                found.append(
                    ("concept.workflow_from", ref, f"exam/pattern/{concept.workflow_from}")
                )
        for link in exam.links:
            found.append(("exam.links", f"exam/concept/{link.start}", f"exam/concept/{link.end}"))
        for pattern in exam.patterns:
            ref = f"exam/pattern/{pattern.key}"
            for key in pattern.concepts:
                found.append(("pattern.concepts", ref, f"exam/concept/{key}"))
            for example in pattern.examples:
                if example.question:
                    found.append(("pattern.examples.question", ref, past[example.question]))
        for sitting in exam.sittings:
            for variant in sitting.variants:
                for question in variant.questions:
                    ref = past[question.key]
                    for key in question.concepts:
                        found.append(("question.concepts", ref, f"exam/concept/{key}"))
                    for key in question.patterns:
                        found.append(("question.patterns", ref, f"exam/pattern/{key}"))
                    for need in question.guidance.prerequisites if question.guidance else ():
                        found.append(
                            ("past.guidance.prerequisites", ref, passage(need.unit, need.block))
                        )
        for mock in exam.mocks:
            for question in mock.questions:
                ref = f"exam/mock/{mock.key}/question/{question.key}"
                for key in question.concepts:
                    found.append(("question.concepts", ref, f"exam/concept/{key}"))
                for key in question.patterns:
                    found.append(("question.patterns", ref, f"exam/pattern/{key}"))
                for key in question.varies_from:
                    found.append(("mock.varies_from", ref, past[key]))
    for lecture in lectures.lectures if lectures else ():
        for entry in lecture.entries:
            if entry.passage:
                found.append(
                    (
                        "lecture.passage",
                        f"lectures/lecture/{lecture.key}/section/{entry.key}",
                        passage(entry.passage.unit, entry.passage.block),
                    )
                )
    return found


def own_sources(inputs) -> dict[str, frozenset[str]]:
    """The source keys each item itself cites; an entry citing none inherits its owner's."""
    cited: dict[str, frozenset[str]] = {}

    def keys(versions) -> frozenset[str]:
        return frozenset(item.key for item in versions)

    for unit in inputs.study.units if inputs.study else ():
        ref = f"study/unit/{unit.key}"
        cited[ref] = keys(unit.sources)
        for block in unit.blocks:
            if block.key:
                cited[f"{ref}/block/{block.key}"] = frozenset(block.sources) or cited[ref]
        for kind, items in (("question", unit.questions), ("flashcard", unit.flashcards)):
            for item in items:
                cited[f"{ref}/{kind}/{item.key}"] = frozenset(item.sources) or cited[ref]
        for item in unit.explore:
            cited[f"{ref}/explore/{item.key}"] = keys(item.sources)
    for group in inputs.exercises.sets if inputs.exercises else ():
        for item in group.exercises:
            ref = f"exercises/set/{group.key}/exercise/{item.key}"
            cited[ref] = keys(item.sources)
            for step in item.steps:
                cited[f"{ref}/step/{step.key}"] = frozenset(step.sources) or cited[ref]
    if exam := inputs.exam:
        for kind, items in (("concept", exam.concepts), ("pattern", exam.patterns)):
            for item in items:
                cited[f"exam/{kind}/{item.key}"] = keys(item.sources)
        for sitting in exam.sittings:
            for variant in sitting.variants:
                ref = f"exam/sitting/{sitting.key}/variant/{variant.key}"
                cited[ref] = keys(variant.sources)
                for question in variant.questions:
                    cited[f"{ref}/question/{question.key}"] = cited[ref]
        for mock in exam.mocks:
            cited[f"exam/mock/{mock.key}"] = keys(mock.sources)
            for question in mock.questions:
                cited[f"exam/mock/{mock.key}/question/{question.key}"] = keys(mock.sources)
    for lecture in inputs.lectures.lectures if inputs.lectures else ():
        ref = f"lectures/lecture/{lecture.key}"
        cited[ref] = keys(lecture.sources)
        for entry in lecture.entries:
            cited[f"{ref}/section/{entry.key}"] = frozenset(entry.sources) or cited[ref]
    return cited


def statement_text(blocks) -> str:
    from tum_mcp.course.memory.graph import safe_text

    return " ".join(safe_text([block.model_dump(mode="json") for block in blocks]).split())[:500]


def statement_queries(inputs) -> list[dict]:
    """Real course sentences as free-text queries; gold is the teaching home they link."""
    rows = []
    concept_units: dict[str, set[str]] = {}
    if exam := inputs.exam:
        for concept in exam.concepts:
            concept_units[concept.key] = set(concept.units) | {p.unit for p in concept.passages}
        for sitting in exam.sittings:
            for variant in sitting.variants:
                for question in variant.questions:
                    gold = set().union(*(concept_units.get(k, set()) for k in question.concepts))
                    if question.guidance:
                        gold |= {need.unit for need in question.guidance.prerequisites}
                    ref = (
                        f"exam/sitting/{sitting.key}/variant/{variant.key}/question/{question.key}"
                    )
                    rows.append((ref, question.statement, gold))
        for mock in exam.mocks:
            for question in mock.questions:
                gold = set().union(*(concept_units.get(k, set()) for k in question.concepts))
                rows.append(
                    (f"exam/mock/{mock.key}/question/{question.key}", question.statement, gold)
                )
    for group in inputs.exercises.sets if inputs.exercises else ():
        for item in group.exercises:
            gold = {need.unit for need in item.prerequisites}
            rows.append((f"exercises/set/{group.key}/exercise/{item.key}", item.statement, gold))
    return [
        {"item": ref, "query": statement_text(blocks), "gold_units": sorted(gold)}
        for ref, blocks, gold in rows
        if gold and blocks and statement_text(blocks)
    ]


@dataclass(frozen=True)
class Selector:
    kind: Literal["context", "impact"]
    args: tuple[tuple[str, object], ...]

    @property
    def key(self) -> str:
        return hashlib.sha256(json.dumps([self.kind, self.args]).encode()).hexdigest()[:16]

    @classmethod
    def context(cls, **args: object) -> "Selector":
        return cls("context", tuple(sorted(args.items())))

    @classmethod
    def impact(cls, **args: object) -> "Selector":
        return cls("impact", tuple(sorted(args.items())))


def build_cases(course: Path, queries: list[dict], heldout: list[dict] = ()) -> dict:
    from tum_mcp.course.memory.store import load_inputs

    inputs = load_inputs(course)
    authored = links(inputs)
    neighbours: dict[str, set[str]] = defaultdict(set)
    families: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for family, start, end in authored:
        neighbours[start].add(end)
        neighbours[end].add(start)
        families[(family, "fwd", start, workspace(end))].add(end)
        families[(family, "rev", end, workspace(start))].add(start)
    fill = [
        {
            "seed": seed,
            "purpose": space,
            "direct": sorted(n for n in near if workspace(n) == space),
            "selector": Selector.context(item=seed, purpose=space, **TEACHING),
        }
        for seed, near in sorted(neighbours.items())
        for space in sorted({workspace(n) for n in near})
    ]
    recall = [
        {
            "family": family,
            "direction": direction,
            "seed": seed,
            "targets": sorted(targets),
            "selector": Selector.context(item=seed, purpose=space, **DEFAULT),
        }
        for (family, direction, seed, space), targets in sorted(families.items())
    ]
    cited = own_sources(inputs)
    owners_by_source: dict[str, set[str]] = defaultdict(set)
    for ref, keys in cited.items():
        for key in keys:
            owners_by_source[key].add(owner(ref))
    impact = [
        {"source": key, "owners": sorted(found), "selector": Selector.impact(source=key, **IMPACT)}
        for key, found in sorted(owners_by_source.items())
    ]
    statements = [
        row | {"selector": Selector.context(query=row["query"], purpose="study", **TEACHING)}
        for row in statement_queries(inputs)
    ]

    def written(rows: list[dict]) -> list[dict]:
        return [
            row
            | {
                "selector": Selector.context(
                    query=row["query"], purpose=row.get("purpose", "study"), **TEACHING
                )
            }
            for row in rows
        ]

    return {
        "fill": fill,
        "recall": recall,
        "impact": impact,
        "statements": statements,
        "written": written(queries),
        "heldout": written(heldout),
        "cited": {ref: sorted(keys) for ref, keys in cited.items()},
        "links": len(authored),
    }


def call(course: Path, selector: Selector) -> dict:
    from tum_mcp.course.memory.query import context, impact
    from tum_mcp.errors import CampusError

    args = dict(selector.args)
    try:
        if selector.kind == "impact":
            return impact(course, args.pop("source"), **args)
        return context(course, **args)
    except CampusError as error:
        return {"error": str(error.code), "message": str(error)[:200]}


def observed_files(course: Path) -> set[Path]:
    """Every file a full-evidence projection reads, so the frozen copy is an exact closure."""
    from tum_mcp.course.memory.evidence import EvidenceChecks
    from tum_mcp.course.memory.projection import project
    from tum_mcp.course.memory.store import load_inputs

    inputs = load_inputs(course)
    graph = project(inputs)
    checks = EvidenceChecks(inputs, full=True)
    for node in graph.nodes.values():
        for version in node.sources:
            checks.source(version)
    for lecture in inputs.lectures.lectures if inputs.lectures else ():
        checks.selection(lecture.key)
    return {path for path, seen in inputs.reader.observations.items() if seen.sha256 is not None}


def freeze(source: Path, name: str) -> dict:
    from tum_mcp.course.project.store import load_state, private_path

    source = source.expanduser().resolve()
    target = corpus(name)
    if target.exists():
        raise LabError(f"Corpus {name} exists; freeze into a new name.")
    with memory_enabled():
        files = observed_files(source)
    state = load_state(source)
    files |= {source / item.path for item in state.resources if item.path}
    for name_ in ("state.json", "coverage.json", "links.json", "knowledge.json", "course.md"):
        files.add(private_path(source, name_))
    files.add(source / "AGENTS.md")
    files |= set((source / "app").rglob("*.json"))
    files |= (
        set(private_path(source, "cache").rglob("*"))
        if private_path(source, "cache").is_dir()
        else set()
    )
    course = target / "course"
    manifest = {}
    for path in sorted(files):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source).as_posix()
        destination = course / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        manifest[relative] = sha(destination)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    queries = target / "queries.json"
    if not queries.exists():
        queries.write_text("[]\n")
    with memory_enabled():
        cases = build_cases(course, [])
        mismatched = [
            case["seed"]
            for case in cases["fill"][:40]
            if call(source, case["selector"]) != call(course, case["selector"])
        ]
    if mismatched:
        raise LabError(f"Frozen copy answers differently for {mismatched[:3]}.")
    size = sum((course / relative).stat().st_size for relative in manifest)
    return {
        "corpus": name,
        "files": len(manifest),
        "bytes": size,
        "verified": len(cases["fill"][:40]),
    }


def check_manifest(name: str) -> Path:
    target = corpus(name)
    manifest = json.loads((target / "manifest.json").read_text())
    course = target / "course"
    changed = [rel for rel, digest in manifest.items() if sha(course / rel) != digest]
    if changed:
        raise LabError(f"Corpus {name} changed since freezing: {changed[:3]}.")
    return course


def identity(name: str) -> dict:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=paths.REPO, capture_output=True, text=True, check=True
        ).stdout.strip()

    memory = sorted((paths.REPO / "src/tum_mcp/course/memory").glob("*.py"))
    return {
        "commit": git("rev-parse", "HEAD"),
        "memory_sources": hashlib.sha256(b"".join(p.read_bytes() for p in memory)).hexdigest(),
        "manifest": sha(corpus(name) / "manifest.json"),
        "queries": sha(corpus(name) / "queries.json"),
        "harness": sha(Path(__file__)),
    }


def mutate(course: Path, source: str, change: str) -> None:
    from tum_mcp.course.project.store import confined, load_state, private_path

    stored = next(s for s in load_state(course).resources if s.resource.key == source)
    path = confined(course, stored.path)
    if change == "bytes":
        data = path.read_bytes()
        path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    elif change == "missing":
        path.unlink()
    else:
        state_path = private_path(course, "state.json")
        value = json.loads(state_path.read_bytes())
        for item in value["resources"]:
            if item["resource"]["key"] == source:
                item["status"] = "withdrawn"
        state_path.write_text(json.dumps(value))


GROUPS = ("fill", "recall", "impact", "statements", "written", "heldout")


def run(name: str, label: str) -> dict:
    course = check_manifest(name)
    output = corpus(name) / "results" / label
    if output.exists():
        raise LabError(f"Result {label} exists; a baseline is never rerun. Use a new label.")
    queries = json.loads((corpus(name) / "queries.json").read_text())
    held = corpus(name) / "queries-heldout.json"
    heldout = json.loads(held.read_text()) if held.is_file() else []
    with memory_enabled():
        cases = build_cases(course, queries, heldout)
        selectors = {
            case["selector"].key: case["selector"] for group in GROUPS for case in cases[group]
        }
        packets = {key: call(course, selector) for key, selector in selectors.items()}
        mutations = run_mutations(course, cases)
        timing_selector = max(cases["fill"], key=lambda c: len(c["direct"]))["selector"]
        samples = []
        for _ in range(7):
            start = time.perf_counter()
            call(course, timing_selector)
            samples.append(time.perf_counter() - start)
    output.mkdir(parents=True)
    serial = {
        group: [case | {"selector": case["selector"].key} for case in cases[group]]
        for group in GROUPS
    }
    (output / "cases.json").write_text(json.dumps(serial | {"cited": cases["cited"]}))
    (output / "packets.json").write_text(json.dumps(packets))
    (output / "mutations.json").write_text(json.dumps(mutations))
    (output / "timing.json").write_text(json.dumps({"seconds": samples}))
    (output / "identity.json").write_text(json.dumps(identity(name), indent=1))
    result = metrics(output)
    (output / "metrics.json").write_text(json.dumps(result, indent=1))
    return result


def run_mutations(course: Path, cases: dict) -> list[dict]:
    """Flip, withdraw or delete the three most-cited sources in a scratch copy."""
    cited = defaultdict(list)
    for ref, keys in cases["cited"].items():
        for key in keys:
            cited[key].append(ref)
    rows = []
    top = sorted(cited, key=lambda key: (-len(cited[key]), key))[:3]
    for source in top:
        for change in ("bytes", "withdrawn", "missing"):
            with tempfile.TemporaryDirectory(prefix="memory-bench-mutation-") as folder:
                scratch = Path(folder) / "course"
                shutil.copytree(course, scratch)
                mutate(scratch, source, change)
                for ref in sorted(cited[source])[:3]:
                    packet = call(
                        scratch, Selector.context(item=ref, purpose=workspace(ref), **TEACHING)
                    )
                    view = next((i for i in packet.get("items", []) if i["id"] == ref), None)
                    rows.append(
                        {
                            "source": source,
                            "change": change,
                            "item": ref,
                            "status": None if view is None else view["evidence_status"],
                            "error": packet.get("error"),
                        }
                    )
    return rows


def metrics(output: Path) -> dict:
    cases = json.loads((output / "cases.json").read_text())
    packets = json.loads((output / "packets.json").read_text())
    mutations = json.loads((output / "mutations.json").read_text())
    samples = json.loads((output / "timing.json").read_text())["seconds"]

    def items(key: str) -> list[str]:
        return [item["id"] for item in packets[key].get("items", [])]

    fill_scores, displaced, hits, fill_bytes = [], 0, 0, 0
    by_pair: dict[str, list[float]] = defaultdict(list)
    for case in cases["fill"]:
        got = [ref for ref in items(case["selector"]) if ref != case["seed"]]
        capacity = min(len(case["direct"]), TEACHING["limit"] - 1)
        found = min(len(set(case["direct"]) & set(got)), capacity)
        score = found / capacity
        fill_scores.append(score)
        displaced += score < 1
        hits += found
        fill_bytes += len(json.dumps(packets[case["selector"]], ensure_ascii=False).encode())
        kind = case["seed"].split("/")[0] + ":" + case["seed"].split("/")[1]
        by_pair[f"{kind} -> {case['purpose']}"].append(score)

    recall: dict[str, list[float]] = defaultdict(list)
    for case in cases["recall"]:
        capacity = min(len(case["targets"]), DEFAULT["limit"] - 1)
        found = min(len(set(case["targets"]) & set(items(case["selector"]))), capacity)
        recall[f"{case['family']} {case['direction']}"].append(found / capacity)
    direction = {
        d: [v for name, values in recall.items() if name.endswith(d) for v in values]
        for d in ("fwd", "rev")
    }

    cited = {ref: set(keys) for ref, keys in cases["cited"].items()}
    locator_errors = []
    for packet in packets.values():
        for view in packet.get("items", []) + packet.get("nodes", []):
            allowed = cited.get(view["id"])
            if allowed is None:
                continue
            for locator in view.get("locators", []):
                if locator.get("kind") == "source" and locator["source"] not in allowed:
                    locator_errors.append(f"{view['id']} -> {locator['source']}")
    locator_errors = sorted(set(locator_errors))

    impact_precision, impact_recall, impact_partial = [], [], 0
    for case in cases["impact"]:
        packet = packets[case["selector"]]
        reported = {owner(ref) for ref in packet.get("direct", [])}
        gold = set(case["owners"])
        if reported:
            impact_precision.append(len(reported & gold) / len(reported))
        if packet.get("status") == "ok":
            impact_recall.append(len(reported & gold) / len(gold) if gold else 1.0)
        else:
            impact_partial += 1

    def ranked(case: dict, gold: set[str]) -> tuple[bool, float]:
        study = [owner(ref) for ref in items(case["selector"]) if ref.startswith("study/")]
        rank = next((i for i, ref in enumerate(study) if ref in gold), None)
        return rank is not None, 0.0 if rank is None else 1 / (rank + 1)

    statements = [
        ranked(case, {f"study/unit/{u}" for u in case["gold_units"]})
        for case in cases["statements"]
    ]

    def scored(case: dict) -> dict:
        packet = packets[case["selector"]]
        got = set(items(case["selector"]))
        if case.get("expect") == "empty":
            ok = packet.get("status") in {"empty", "partial"} and not (
                got & set(case.get("forbidden", []))
            )
            return {"id": case["id"], "ok": ok, "rr": 1.0 if ok else 0.0, "forbidden": 0}
        required = set(case["required"])
        order = items(case["selector"])
        rank = next((i for i, ref in enumerate(order) if ref in required), None)
        return {
            "id": case["id"],
            "ok": required <= got,
            "rr": 0.0 if rank is None else 1 / (rank + 1),
            "forbidden": len(got & set(case.get("forbidden", []))),
            "top": order[:1],
            "group": case.get("group"),
        }

    written = [scored(case) for case in cases["written"]]
    heldout = [scored(case) for case in cases.get("heldout", [])]
    impact_bytes = [
        len(json.dumps(packets[case["selector"]], separators=(",", ":")))
        for case in cases["impact"]
    ]
    groups: dict[str, set[str]] = defaultdict(set)
    for row in written:
        if row.get("group"):
            groups[row["group"]].add(tuple(row.get("top", [])) and row["top"][0])
    flagged = [row for row in mutations if row["status"] != "current"]

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    return {
        "direct_fill_at_4": {
            "mean": mean(fill_scores),
            "pairs": len(fill_scores),
            "displaced": displaced,
            "by_pair": {k: mean(v) for k, v in sorted(by_pair.items())},
        },
        "capped_recall_at_12": {
            "fwd": mean(direction["fwd"]),
            "rev": mean(direction["rev"]),
            "by_family": {k: mean(v) for k, v in sorted(recall.items())},
        },
        "locator_errors": {"count": len(locator_errors), "examples": locator_errors[:8]},
        "impact": {
            "precision": mean(impact_precision),
            "recall_complete_packets": mean(impact_recall),
            "partial_packets": impact_partial,
            "sources": len(cases["impact"]),
            "mean_bytes": round(statistics.mean(impact_bytes)) if impact_bytes else None,
        },
        "mutations": {"flagged": len(flagged), "total": len(mutations)},
        "statement_queries": {
            "n": len(statements),
            "hit_at_4": mean([float(hit) for hit, _ in statements]),
            "mrr": mean([rr for _, rr in statements]),
        },
        "written_queries": {
            "n": len(written),
            "ok": sum(row["ok"] for row in written),
            "mrr": mean([row["rr"] for row in written]),
            "forbidden_hits": sum(row["forbidden"] for row in written),
            "paraphrase_groups_agreeing": sum(len(tops) == 1 for tops in groups.values()),
            "paraphrase_groups": len(groups),
        },
        "heldout_queries": {
            "n": len(heldout),
            "ok": sum(row["ok"] for row in heldout),
            "mrr": mean([row["rr"] for row in heldout]),
            "missed": [row["id"] for row in heldout if not row["ok"]],
        },
        "bytes_per_authored_hit": round(fill_bytes / hits) if hits else None,
        "latency_seconds": {
            "median": round(statistics.median(samples), 4),
            "max": round(max(samples), 4),
        },
    }


def compare(name: str, base: str, candidate: str) -> dict:
    results = corpus(name) / "results"
    left, right = metrics(results / base), metrics(results / candidate)

    def flat(value: object, prefix: str = "") -> dict[str, object]:
        if isinstance(value, dict):
            out: dict[str, object] = {}
            for key, item in value.items():
                out |= flat(item, f"{prefix}{key}.")
            return out
        return {prefix.rstrip("."): value}

    a, b = flat(left), flat(right)
    return {key: {"base": a.get(key), "candidate": b.get(key)} for key in sorted(a | b)}
