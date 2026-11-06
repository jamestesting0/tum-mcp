"""Executable answer keys: `.tum-mcp/checks/<item>.py` computes what an item must say, and
`study verify` compares it with the content.

A script prints one JSON object:

- `values`: content path -> expected value. The text at the path must contain the value; a
  number must equal it within 1e-9 (relative).
- `walkthroughs`: walkthrough block key -> one object per step, label -> expected state row.

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
    for key, steps in (output.get("walkthroughs") or {}).items():
        block = _walkthrough(value, key)
        if block is None:
            problems.append(f"walkthrough {key}: not in the content")
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
            {"item": key, "passed": not problems, "compared": compared, "problems": problems}
        )
    return results
