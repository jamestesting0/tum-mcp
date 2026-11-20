"""Executable answer keys: `.tum-mcp/checks/<item>.py` computes what an item must say, and
`study verify` compares it with the content.

A script prints one JSON object:

- `values`: content path -> expected value. The text at the path must contain the value; a
  number must equal it within 1e-9 (relative).
- `exact_values`: content path -> complete expected value, with whitespace normalized in text.
- `walkthroughs`: walkthrough block key -> runs (`primary`, and `variant` when authored).
  Each run lists one object per step containing all state rows, matched exactly, and
  `"@node_values"`: node key -> value when the stage writes values under its nodes;
  `"@cutoff"`: node keys cut off at this step, when supplied by the key;
  `"@discarded"`: rejected or pruned node keys at this step, when supplied by the key;
  `"@grid"`: "grid:row:column" -> the value a grid stage shows in that cell after this
  step (authored cells plus every `grid_values` change so far in the run).
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
from typing import TypedDict

from pydantic import JsonValue, TypeAdapter, ValidationError

from tum_mcp.course.project.store import confined

TIMEOUT_S = 30
# In a walkthrough step's expected state, the values written under its nodes.
NODE_VALUES = "@node_values"
GRID = "@grid"
STEP = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
NUMBER_TEXT = r"[+-]?(?:[0-9]+(?:[.,][0-9]+)*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
NUMBER = re.compile(NUMBER_TEXT)
STANDALONE_NUMBER = re.compile(rf"(?<![\w.,+-]){NUMBER_TEXT}(?![\w+-]|[.,][0-9])")

type ExpectedRows = list[dict[str, JsonValue]]


class KeyOutput(TypedDict, total=False):
    values: dict[str, JsonValue]
    exact_values: dict[str, JsonValue]
    walkthroughs: dict[str, ExpectedRows | dict[str, ExpectedRows]]


KEY_OUTPUT = TypeAdapter(KeyOutput)


def script_path(root: Path, item: str) -> Path:
    return confined(root, f".tum-mcp/checks/{item}.py")


def run_key(root: Path, item: str) -> dict:
    """The script's output, or a `problem` saying why it gave none."""
    path = script_path(root, item)
    with tempfile.TemporaryDirectory() as folder:
        try:
            done = subprocess.run(  # noqa: S603 - the project's own answer key, run isolated
                [sys.executable, "-I", "-X", "utf8", str(path)],
                cwd=folder,
                capture_output=True,
                timeout=TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"problem": f"the answer key ran past {TIMEOUT_S} s"}
    if done.returncode:
        detail = done.stderr.decode("utf-8", errors="replace").strip()[-400:]
        return {"problem": f"the answer key failed: {detail}"}
    try:
        output = json.loads(done.stdout.decode("utf-8"))
    except UnicodeDecodeError:
        return {"problem": "the answer key did not print UTF-8"}
    except (ValueError, RecursionError):
        return {"problem": "the answer key printed no JSON object"}
    return output if isinstance(output, dict) else {"problem": "the answer key printed no object"}


def at(value: JsonValue, path: str) -> JsonValue:
    for name, index in STEP.findall(path):
        value = value[int(index)] if index else value[name]  # type: ignore[index]
    return value


def _same(found: JsonValue, expected: JsonValue) -> bool:
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        if isinstance(found, bool):
            return False
        if isinstance(found, int | float):
            number = found
        elif isinstance(found, str):
            text = found.replace("−", "-")
            # Count attached quantities too. They make the text ambiguous even
            # when one standalone number matches the answer key.
            tokens = list(NUMBER.finditer(text))
            if len(tokens) != 1:
                return False
            token = tokens[0]
            literal = token[0]
            standalone = STANDALONE_NUMBER.match(text, token.start())
            if (
                standalone is None
                or standalone.end() != token.end()
                or literal.count(".") > 1
                or "," in literal
            ):
                return False
            number = float(literal)
        else:
            return False
        try:
            return (
                math.isfinite(number)
                and math.isfinite(expected)
                and math.isclose(number, expected, rel_tol=1e-9, abs_tol=1e-12)
            )
        except OverflowError:
            return False
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
            roles = False
            for role in ("cutoff", "discarded"):
                field = f"@{role}"
                if isinstance(states, dict) and field in states:
                    roles = True
                    expected_role = states[field]
                    states = {label: state for label, state in states.items() if label != field}
                    compared += 1
                    found_role = step.get(role, [])
                    if not _exact(found_role, expected_role):
                        problems.append(
                            f"{place}: {role} is {found_role!r}, the key computes {expected_role!r}"
                        )
            grid = isinstance(states, dict) and GRID in states
            if grid:
                board = _board(block, steps[:number])
                expected_cells = states[GRID]
                states = {label: state for label, state in states.items() if label != GRID}
                if not isinstance(expected_cells, dict):
                    problems.append(f"{place}: expected grid cells as an object.")
                    continue
                for cell, value in expected_cells.items():
                    compared += 1
                    if not _exact(board.get(cell), value):
                        problems.append(
                            f"{place}: cell {cell} shows {board.get(cell)!r}, "
                            f"the key computes {value!r}"
                        )
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
                or not (states or values is not None or roles or grid)
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


def _board(block: dict, steps: list[dict]) -> dict[str, str]:
    """Every cell of a grid stage as shown after the given steps."""
    board = {
        f"{grid['key']}:{row}:{column}": value
        for grid in (block.get("stage") or {}).get("grids", [])
        for row, cells in enumerate(grid["cells"], 1)
        for column, value in enumerate(cells, 1)
    }
    for step in steps:
        for item in step.get("grid_values", []):
            board[f"{item['grid']}:{item['cell']}"] = item["value"]
    return board


def compare(value: JsonValue, output: dict) -> tuple[list[str], int]:
    """The differences between an item's content and its answer key, and how many values
    were compared."""
    problems, compared, _, _ = _comparison(value, KEY_OUTPUT.validate_python(output, strict=True))
    return problems, compared


def _comparison(value: JsonValue, output: KeyOutput) -> tuple[list[str], int, set[str], set[str]]:
    problems: list[str] = []
    compared = 0
    matched_values: set[str] = set()
    matched_walkthroughs: set[str] = set()
    for path, expected in (output.get("values") or {}).items():
        try:
            found = at(value, path)
        except (KeyError, IndexError, TypeError):
            problems.append(f"{path}: no such place in the content")
            continue
        compared += 1
        if not _same(found, expected):
            message = f"{path}: the key computes {expected!r}, the content says {found!r}"
            if isinstance(expected, int | float) and not isinstance(expected, bool):
                message += ". Compare a numeric field or text containing one numeric value."
            problems.append(message)
        else:
            matched_values.add(path)
    for path, expected in (output.get("exact_values") or {}).items():
        try:
            found = at(value, path)
        except (KeyError, IndexError, TypeError):
            problems.append(f"{path}: no such place in the content")
            continue
        compared += 1
        if not _exact(found, expected):
            problems.append(f"{path}: the key computes {expected!r}, the content says {found!r}")
        else:
            matched_values.add(path)
    for key, steps in (output.get("walkthroughs") or {}).items():
        start_count, start_problems = compared, len(problems)
        block = _walkthrough(value, key)
        if block is None:
            problems.append(f"walkthrough {key}: not in the content")
            continue
        if isinstance(steps, dict):
            failures, count = _compare_runs(block, steps, key)
            problems.extend(failures)
            compared += count
            if count and not failures:
                matched_walkthroughs.add(key)
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
        if compared > start_count and len(problems) == start_problems:
            matched_walkthroughs.add(key)
    return problems, compared, matched_values, matched_walkthroughs


def verify(root: Path, items: dict, only: str | None = None) -> list[dict[str, JsonValue]]:
    """Run answer keys for the supplied item inventory against current content."""
    results: list[dict[str, JsonValue]] = []
    for key, item in sorted(items.items()):
        if (only and key != only) or "answer-key" not in item.blocks:
            continue
        output = run_key(root, key)
        if "problem" in output:
            results.append(
                {
                    "item": key,
                    "passed": False,
                    "status": "failed",
                    "compared": 0,
                    "problems": [str(output["problem"])],
                }
            )
            continue
        try:
            parsed = KEY_OUTPUT.validate_python(output, strict=True)
        except ValidationError as error:
            field = ".".join(str(part) for part in error.errors()[0]["loc"])
            results.append(
                {
                    "item": key,
                    "passed": False,
                    "status": "failed",
                    "compared": 0,
                    "problems": [f"the answer key returned malformed {field or 'output'}"],
                }
            )
            continue
        problems, compared, matched_values, matched_walkthroughs = _comparison(item.value, parsed)
        status = "failed" if problems else "passed" if compared else "no_checks"
        if status == "no_checks":
            problems.append("the answer key compares nothing")
        results.append(
            {
                "item": key,
                "passed": not problems,
                "status": status,
                "compared": compared,
                "matched_values": sorted(matched_values),
                "matched_walkthroughs": sorted(matched_walkthroughs),
                "problems": problems,
                "values": sorted(
                    parsed.get("values", {}).keys() | parsed.get("exact_values", {}).keys()
                ),
                "exact_values": sorted(parsed.get("exact_values", {})),
                "checked_runs": {
                    name: {run: len(rows) for run, rows in steps.items() if isinstance(rows, list)}
                    for name, steps in parsed.get("walkthroughs", {}).items()
                    if isinstance(steps, dict)
                },
                "walkthroughs": sorted(
                    name
                    for name, steps in parsed.get("walkthroughs", {}).items()
                    if steps and all(steps)
                ),
            }
        )
    return results
