"""Fixed synthetic inputs and transparent counters for local, model-free profiling."""

import copy
import hashlib
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path

import pytest
from knowledge_annotations import annotation, write_registry
from knowledge_fixture import knowledge_project

from tum_mcp import study_knowledge_query as query
from tum_mcp.study_content import StudyContent
from tum_mcp.study_knowledge_assertions import AssertionChecks, review_revision
from tum_mcp.study_knowledge_packet import encoded
from tum_mcp.study_knowledge_projection import project
from tum_mcp.study_knowledge_report import knowledge_revision
from tum_mcp.study_knowledge_store import SnapshotReader, load_inputs
from tum_mcp.study_models import StudyState
from tum_mcp.study_store import private_path

REPO = Path(__file__).resolve().parents[2]
EXERCISE = "exercises/set/sheet-1/exercise/observer-practice"


def scaled_course(folder: Path, units: int, *, crowded: bool = False) -> Path:
    root = knowledge_project(folder, workspaces=frozenset({"study", "exercises"}))
    content_path = root / "app/content.json"
    content = json.loads(content_path.read_bytes())
    state_path = private_path(root, "state.json")
    state = json.loads(state_path.read_bytes())
    original = next(s for s in state["resources"] if s["resource"]["key"] == "slides")
    template = content["units"][0]
    content["units"] = []
    for i in range(units):
        unit = copy.deepcopy(template)
        unit.update(key=f"unit-{i:03}", title=f"Topic {i}", lectures=[], explore=[])
        if crowded:
            resource = copy.deepcopy(original)
            key = f"source-{i:03}"
            body = f"Synthetic evidence for topic {i}.".encode()
            relative = f"materials/content/material-{key}.md"
            (root / relative).write_bytes(body)
            sha = hashlib.sha256(body).hexdigest()
            resource.update(path=relative, sha256=sha)
            resource["resource"].update(key=key, title=f"Topic {i}")
            state["resources"].append(resource)
            unit["sources"] = [{"key": key, "sha256": sha}]
            for value in unit["flashcards"] + unit["questions"]:
                value["sources"] = [key]
                for block in value.get("blocks", []):
                    block["sources"] = [key]
            unit["blocks"] = [
                {
                    "kind": "text",
                    "key": f"passage-{j:02}",
                    "title": f"Passage {j}",
                    "paragraphs": [f"Topic {i} has source-backed statement {j}."],
                    "sources": [key],
                    "pages": "1",
                }
                for j in range(20)
            ]
        content["units"].append(unit)
    content_path.write_text(
        StudyContent.model_validate(content).model_dump_json(), encoding="utf-8"
    )
    state_path.write_text(StudyState.model_validate(state).model_dump_json(), encoding="utf-8")
    path = root / "app/exercises.json"
    exercises = json.loads(path.read_bytes())
    exercises["sets"][0]["exercises"][0]["prerequisites"] = [
        {"unit": f"unit-{i:03}", "explanation": "Use this foundation."}
        for i in range(min(units, 10))
    ]
    path.write_text(json.dumps(exercises), encoding="utf-8")
    private_path(root, "coverage.json").unlink()
    graph = project(load_inputs(root))
    if crowded:
        routes, exhausted = query.walk(
            graph, [EXERCISE], AssertionChecks(graph, query.EvidenceChecks(graph.inputs))
        )
        assert 200 < len(routes) < 256 and not exhausted
    return root


def mixed_registry(folder: Path) -> Path:
    root = knowledge_project(folder, workspaces=frozenset({"study"}))
    rows = [annotation(root, key=f"claim-{i:03}") for i in range(200)]
    for i, row in enumerate(rows):
        row["conditions"] = [f"Synthetic scope {i}."]
        if i >= 104:
            row["review"]["status"] = "rejected"
    write_registry(root, rows)
    graph = project(load_inputs(root))
    for row in rows[:8]:
        row["review"] = {
            "status": "reviewed",
            "revision": review_revision(graph, graph.assertions[row["key"]]),
        }
    write_registry(root, rows)
    return root


def measured_context(root: Path, *, limit: int = 4, max_bytes: int = 65536) -> dict:
    """Wrap real operations; count work without replacing evidence or clock results."""
    counts = Counter()
    stages = Counter()
    verifying = False
    original_hash = SnapshotReader.fingerprint
    original_verify = SnapshotReader.verify
    original_view = query.item_view

    def fingerprint(reader, path, bound):
        prefix = "verify" if verifying else "initial"
        counts[f"{prefix}_hash_calls"] += 1
        counts[f"{prefix}_hash_bytes"] += path.stat().st_size if path.is_file() else 0
        return original_hash(reader, path, bound)

    def verify(reader):
        nonlocal verifying
        verifying = True
        start = time.perf_counter()
        try:
            return original_verify(reader)
        finally:
            stages["verify"] += time.perf_counter() - start
            verifying = False

    def view(node, evidence):
        counts["item_views"] += 1
        return original_view(node, evidence)

    def timed(function, name):
        def call(*args, **kwargs):
            start = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                stages[name] += time.perf_counter() - start

        return call

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(SnapshotReader, "fingerprint", fingerprint)
        patch.setattr(SnapshotReader, "verify", verify)
        patch.setattr(query, "item_view", view)
        for name in ("load_inputs", "project", "walk", "fit"):
            patch.setattr(query, name, timed(getattr(query, name), name))
        start = time.perf_counter()
        packet = query.context(root, item=EXERCISE, limit=limit, max_bytes=max_bytes)
        elapsed = time.perf_counter() - start
    return {
        "seconds": elapsed,
        "stages": dict(stages),
        "work": dict(counts),
        "bytes": len(encoded(packet)),
        "ids": [i["id"] for i in packet["items"]],
        "status": packet["status"],
    }


def profile(folder: Path) -> dict:
    import platform

    datasets = {}
    for size in (14, 100, 300):
        location = folder / f"scale-{size}"
        location.mkdir()
        datasets[f"scale-{size}"] = scaled_course(location, size)
    location = folder / "crowded"
    location.mkdir()
    datasets["crowded"] = scaled_course(location, 10, crowded=True)
    results = {}
    for name, root in datasets.items():
        rows = {}
        for limit, budget in ((4, 8000), (12, 24000), (4, 65536)):
            for _ in range(2):
                measured_context(root, limit=limit, max_bytes=budget)
            samples = [measured_context(root, limit=limit, max_bytes=budget) for _ in range(7)]
            rows[f"{limit}/{budget}"] = {
                "samples": samples,
                "median_seconds": statistics.median(s["seconds"] for s in samples),
            }
        tracemalloc.start()
        measured_context(root)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows["peak_python_bytes"] = peak
        results[name] = rows
    location = folder / "registry"
    location.mkdir()
    root = mixed_registry(location)
    registry_samples = []
    for _ in range(9):
        start = time.perf_counter()
        revision = knowledge_revision(root)
        registry_samples.append(time.perf_counter() - start)
    cli = []
    for _ in range(7):
        start = time.perf_counter()
        result = subprocess.run(  # noqa: S603 - fixed local CLI, isolated synthetic course
            [
                sys.executable,
                "-m",
                "tum_mcp",
                "study",
                "context",
                str(root),
                "--item",
                "study/unit/observer",
                "--limit",
                "4",
                "--max-bytes",
                "8000",
            ],
            cwd=REPO,
            capture_output=True,
            check=True,
            text=True,
            timeout=60,
        )
        assert json.loads(result.stdout)["items"]
        cli.append(time.perf_counter() - start)
    import tum_mcp

    assert Path(tum_mcp.__file__).resolve().is_relative_to(REPO / "src")
    files = [
        Path(__file__),
        REPO / "tests/fixtures/study_knowledge/efficiency-cases.json",
        Path(__file__).with_name("knowledge_fixture.py"),
        Path(__file__).with_name("knowledge_annotations.py"),
        Path(__file__).with_name("material_fixture.py"),
    ]
    product = sorted((REPO / "src/tum_mcp").glob("study_knowledge*.py"))
    product_digest = hashlib.sha256(
        b"".join(p.name.encode() + p.read_bytes() for p in product)
    ).hexdigest()
    return {
        "product_digest": product_digest,
        "python": sys.version,
        "platform": platform.platform(),
        "module_root": str(Path(tum_mcp.__file__).resolve()),
        "harness_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "datasets": results,
        "revision": revision,
        "revision_samples": registry_samples[2:],
        "revision_median_seconds": statistics.median(registry_samples[2:]),
        "cli_samples": cli,
        "cli_median_seconds": statistics.median(cli),
    }
