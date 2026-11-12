"""Executable answer keys: `.tum-mcp/checks/<item>.py` computes what an item must say, and
`study verify` compares it with the content.

A script prints one JSON object:

- `values`: content path -> expected value. The text at the path must contain the value; a
  number must equal it within 1e-9 (relative).
- `exact_values`: content path -> complete expected value, with whitespace normalized in text.
- `walkthroughs`: walkthrough block key -> runs (`primary`, and `variant` when authored).
  Each run lists one object per step containing all state rows, matched exactly, and
  `"@node_values"`: node key -> value when the stage writes values under its nodes.
  A list of partial primary-run states is accepted for legacy keys.

Scripts run isolated (`python -I`) in an empty folder with a time limit.
"""

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.course.project.store import confined

TIMEOUT_S = 30
# In a walkthrough step's expected state, the values written under its nodes.
NODE_VALUES = "@node_values"
STEP = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def script_path(root: Path, item: str) -> Path:
    return confined(root, f".tum-mcp/checks/{item}.py")


def run_key(root: Path, item: str) -> dict:
    """The script's output, or a `problem` saying why it gave none."""
    path = script_path(root, item)
    with tempfile.TemporaryDirectory() as folder:
        try:
            done = subprocess.run(  # noqa: S603 - the project's own answer key, run isolated
                [sys.executable, "-I", str(path)],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"problem": f"the answer key ran past {TIMEOUT_S} s"}
    if done.returncode:
        return {"problem": f"the answer key failed: {done.stderr.strip()[-400:]}"}
    try:
        output = json.loads(done.stdout)
    except json.JSONDecodeError:
        return {"problem": "the answer key printed no JSON object"}
    return output if isinstance(output, dict) else {"problem": "the answer key printed no object"}


def at(value: JsonValue, path: str) -> JsonValue:
    for name, index in STEP.findall(path):
        value = value[int(index)] if index else value[name]  # type: ignore[index]
    return value


def _same(found: JsonValue, expected: JsonValue) -> bool:
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        try:
            number = float(str(found).strip())
        except ValueError:
            return str(expected) in " ".join(str(found).split())
        return math.isclose(number, expected, rel_tol=1e-9, abs_tol=1e-12)
    return " ".join(str(expected).split()) in " ".join(str(found).split())


def _walkthrough(value: JsonValue, key: str) -> dict | None:
    if isinstance(value, dict):
        if value.get("kind") == "walkthrough" and value.get("key") == key:
            return value
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return None
    return next((found for child in children if (found := _walkthrough(child, key))), None)


def _exact(found: JsonValue, expected: JsonValue) -> bool:
    if isinstance(found, str) and isinstance(expected, str):
        return found.split() == expected.split()
    return type(found) is type(expected) and found == expected


def _compare_runs(block: dict, runs: dict, key: str) -> tuple[list[str], int]:
    written = {"primary": block["steps"]}
    if block.get("variant"):
        written["variant"] = block["variant"]["steps"]
    if runs.keys() != written.keys():
        return [f"walkthrough {key}: expected primary and authored variant runs exactly."], 0
    problems = []
    compared = 0
    for run, steps in written.items():
        expected = runs[run]
        if not isinstance(expected, list) or len(expected) != len(steps):
            problems.append(f"walkthrough {key}/{run}: expected {len(steps)} steps.")
            continue
        for number, (step, states) in enumerate(zip(steps, expected, strict=True), 1):
            rows = step.get("state", [])
            actual = {row["label"]: row["value"] for row in rows}
            place = f"walkthrough {key}/{run} step {number}"
            values = None
            if isinstance(states, dict) and NODE_VALUES in states:
                values = states[NODE_VALUES]
                states = {label: state for label, state in states.items() if label != NODE_VALUES}
                found = step.get("node_values", {})
                if not isinstance(values, dict) or values.keys() != found.keys():
                    problems.append(f"{place}: expected the value under each node exactly.")
                    continue
                for node, value in values.items():
                    compared += 1
                    if not _exact(found[node], value):
                        problems.append(
                            f"{place}: node {node} shows {found[node]!r}, "
                            f"the key computes {value!r}"
                        )
            if (
                not isinstance(states, dict)
                or not (states or values is not None)
                or (states.keys() != actual.keys() or len(actual) != len(rows))
            ):
                problems.append(f"{place}: expected each authored state row exactly once.")
                continue
            for label, state in states.items():
                compared += 1
                if not _exact(actual[label], state):
                    problems.append(
                        f"{place}: {label} is {actual[label]!r}, the key computes {state!r}"
                    )
    return problems, compared


def compare(value: JsonValue, output: dict) -> tuple[list[str], int]:
    """The differences between an item's content and its answer key, and how many values
    were compared."""
    problems: list[str] = []
    compared = 0
    for path, expected in (output.get("values") or {}).items():
        compared += 1
        try:
            found = at(value, path)
        except (KeyError, IndexError, TypeError):
            problems.append(f"{path}: no such place in the content")
            continue
        if not _same(found, expected):
            problems.append(f"{path}: the key computes {expected!r}, the content says {found!r}")
    for path, expected in (output.get("exact_values") or {}).items():
        compared += 1
        try:
            found = at(value, path)
        except (KeyError, IndexError, TypeError):
            problems.append(f"{path}: no such place in the content")
            continue
        if not _exact(found, expected):
            problems.append(f"{path}: the key computes {expected!r}, the content says {found!r}")
    for key, steps in (output.get("walkthroughs") or {}).items():
        block = _walkthrough(value, key)
        if block is None:
            problems.append(f"walkthrough {key}: not in the content")
            continue
        if isinstance(steps, dict):
            failures, count = _compare_runs(block, steps, key)
            problems.extend(failures)
            compared += count
            continue
        written = block["steps"]
        if len(written) != len(steps):
            problems.append(f"walkthrough {key}: {len(written)} steps, the key has {len(steps)}")
        for number, (step, expected) in enumerate(zip(written, steps, strict=False), 1):
            rows = {row["label"]: row["value"] for row in step.get("state", [])}
            for label, state in expected.items():
                compared += 1
                if label not in rows or not _same(rows[label], state):
                    problems.append(
                        f"walkthrough {key} step {number}: {label} is {rows.get(label)!r}, "
                        f"the key computes {state!r}"
                    )
    return problems, compared


def verify(root: Path, items: dict, only: str | None = None) -> list[dict[str, JsonValue]]:
    """Run every answer key (or one item's) against its item's current content."""
    results: list[dict[str, JsonValue]] = []
    for key, item in sorted(items.items()):
        if (only and key != only) or "answer-key" not in item.blocks:
            continue
        output = run_key(root, key)
        if "problem" in output:
            results.append({"item": key, "passed": False, "problems": [output["problem"]]})
            continue
        problems, compared = compare(item.value, output)
        if not compared:
            problems.append("the answer key compares nothing")
        results.append(
            {
                "item": key,
                "passed": not problems,
                "compared": compared,
                "problems": problems,
                "values": sorted(
                    (output.get("values") or {}).keys() | (output.get("exact_values") or {}).keys()
                ),
                "exact_values": sorted(output.get("exact_values") or {}),
                "checked_runs": {
                    name: {run: len(rows) for run, rows in steps.items() if isinstance(rows, list)}
                    for name, steps in (output.get("walkthroughs") or {}).items()
                    if isinstance(steps, dict)
                },
                "walkthroughs": sorted(
                    name
                    for name, steps in (output.get("walkthroughs") or {}).items()
                    if steps and all(steps)
                ),
            }
        )
    return results
