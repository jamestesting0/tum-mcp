"""Seeded-defect calibration: plant known defects into a restored course before a review turn,
then measure how many the review found, per dimension.

Planted defects are easier to see than real ones, so recall is an upper bound; a skill or
rubric change must not lower it. Every defect keeps the course valid, so the build still runs.
"""

import json
import re
from pathlib import Path

from skill_lab import LabError

META_LINE = "This section explains the idea that follows."
DESCRIBED = "Students often get this step wrong."


def _project(workspace: Path) -> Path:
    states = sorted(workspace.glob("**/.tum-mcp/state.json"))
    if not states:
        raise LabError(f"No course project under {workspace}.")
    return states[0].parent.parent


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _texts(unit: dict) -> list[dict]:
    return [
        block for block in unit["blocks"] if block.get("kind") == "text" and block.get("paragraphs")
    ]


def _meta_line(content: dict, _exam: dict | None, touched: set[int]) -> dict | None:
    for unit in content["units"]:
        for block in _texts(unit):
            touched.add(id(block))
            block["paragraphs"][0] = f"{META_LINE} {block['paragraphs'][0]}"
            return {"item": f"study/{unit['key']}", "probe": META_LINE}
    return None


def _point_last(content: dict, _exam: dict | None, touched: set[int]) -> dict | None:
    for unit in content["units"][1:] + content["units"][:1]:
        for block in _texts(unit):
            for index, paragraph in enumerate(block["paragraphs"]):
                sentences = re.split(r"(?<=[.!?])\s+", paragraph)
                if len(sentences) >= 3 and id(block) not in touched:
                    touched.add(id(block))
                    moved = " ".join([*sentences[1:], sentences[0]])
                    block["paragraphs"][index] = moved
                    return {"item": f"study/{unit['key']}", "probe": moved}
    return None


def _dropped_link(content: dict, _exam: dict | None, touched: set[int]) -> dict | None:
    for unit in reversed(content["units"]):
        titled = [
            b
            for b in _texts(unit)[1:]
            if b.get("title") and len(b["paragraphs"]) >= 2 and id(b) not in touched
        ]
        if titled:
            touched.add(id(titled[0]))
            removed = titled[0]["paragraphs"].pop(0)
            return {
                "item": f"study/{unit['key']}",
                "detail": removed[:120],
                "section": titled[0]["title"],
                "opening": titled[0]["paragraphs"][0],
            }
    return None


def _wrong_result(content: dict, _exam: dict | None, touched: set[int]) -> dict | None:
    for unit in content["units"]:
        for block in unit["blocks"]:
            if block.get("kind") != "derivation":
                continue
            line = block["groups"][-1]["lines"][-1]
            digits = [m for m in re.finditer(r"\d", line["latex"])]
            if digits:
                at = digits[-1].start()
                changed = str((int(line["latex"][at]) + 1) % 10)
                line["latex"] = line["latex"][:at] + changed + line["latex"][at + 1 :]
                return {"item": f"study/{unit['key']}", "probe": line["latex"]}
    return None


def _meaning_removed(content: dict, _exam: dict | None, touched: set[int]) -> dict | None:
    for unit in content["units"]:
        for block in unit["blocks"]:
            if block.get("kind") == "derivation" and block.get("symbols"):
                removed = [item["symbol"] for item in block["symbols"]]
                block["symbols"] = []
                return {
                    "item": f"study/{unit['key']}",
                    "detail": ", ".join(removed),
                    "section": block.get("title"),
                }
    return None


def _described_pitfall(_content: dict, exam: dict | None, touched: set[int]) -> dict | None:
    for pattern in (exam or {}).get("patterns", []):
        if pattern.get("pitfalls"):
            pattern["pitfalls"][0]["wrong"] = DESCRIBED
            return {"item": f"exam/pattern/{pattern['key']}", "probe": DESCRIBED}
    return None


def _late_prerequisite(content: dict, _exam: dict | None, touched: set[int]) -> dict | None:
    # The unit's last titled section, with its continuations, moved before its first.
    for unit in content["units"]:
        starts = [
            i for i, b in enumerate(unit["blocks"]) if b.get("title") and (b.get("level") or 1) == 1
        ]
        if len(starts) >= 3:
            last = unit["blocks"][starts[-1] :]
            unit["blocks"][starts[0] : starts[0]] = last
            del unit["blocks"][-len(last) :]
            return {"item": f"study/{unit['key']}", "detail": last[0]["title"]}
    return None


def _unit(content: dict, item: str) -> dict | None:
    return next((u for u in content["units"] if f"study/{u['key']}" == item), None)


def _probe_gone(text: str, _content: dict, defect: dict) -> bool:
    return json.dumps(defect["probe"])[1:-1] not in text


def _opening_back(_text: str, content: dict, defect: dict) -> bool:
    # The section is gone, renamed, or opens with something new again.
    unit = _unit(content, defect["item"]) or {"blocks": []}
    section = next((b for b in unit["blocks"] if b.get("title") == defect["section"]), None)
    return section is None or (section.get("paragraphs") or [None])[0] != defect["opening"]


def _meanings_back(_text: str, content: dict, defect: dict) -> bool:
    unit = _unit(content, defect["item"]) or {"blocks": []}
    block = next(
        (
            b
            for b in unit["blocks"]
            if b.get("kind") == "derivation" and b.get("title") == defect["section"]
        ),
        None,
    )
    return block is None or bool(block.get("symbols"))


def _order_back(_text: str, content: dict, defect: dict) -> bool:
    unit = _unit(content, defect["item"]) or {"blocks": []}
    first = next((b.get("title") for b in unit["blocks"] if b.get("title")), None)
    return first != defect["detail"]


# Each defect: the dimension it lowers, how it is planted, and how to tell it was undone.
DEFECTS = {
    "meta_line": ("clarity", _meta_line, _probe_gone),
    "point_last": ("cohesion", _point_last, _probe_gone),
    "dropped_link": ("cohesion", _dropped_link, _opening_back),
    "wrong_result": ("correctness", _wrong_result, _probe_gone),
    "meaning_removed": ("clarity", _meaning_removed, _meanings_back),
    "described_pitfall": ("representation", _described_pitfall, _probe_gone),
    "late_prerequisite": ("organization", _late_prerequisite, _order_back),
}

CHECKS = {
    "meta_line": "clarity.no_meta",
    "point_last": "cohesion.point_first",
    "dropped_link": "cohesion.linked",
    "wrong_result": "correctness.recomputed",
    "meaning_removed": "clarity.symbols_recall",
    "described_pitfall": "representation.shown_not_described",
    "late_prerequisite": "organization.dependency_order",
    "dense_section": "cognitive_load.short_prose",
    "empty_feedback": "practice.plausible_options",
    "unpractised_outcome": "coverage.ledger_outcomes",
    "missing_reason": "intuition.reasons",
    "repeated_caption": "redundancy.text_restates_picture",
}


def _extra_defects(content: dict, touched: set[int]) -> list[dict]:
    planted = {}

    def replace(name: str, unit: dict, target: dict, field: str, value: str) -> None:
        if name not in planted and id(target) not in touched:
            target[field] = value
            touched.add(id(target))
            planted[name] = {
                "defect": name,
                "check": CHECKS[name],
                "dimension": CHECKS[name].split(".")[0],
                "item": f"study/{unit['key']}",
                "probe": value,
            }

    for unit in content["units"]:
        for question in unit.get("questions", []):
            for option in question["options"]:
                if option["key"] != question["correct"]:
                    replace("empty_feedback", unit, option, "feedback", "Not this option.")
            replace(
                "unpractised_outcome",
                unit,
                question,
                "prompt",
                "Which month has the fewest days in a common year?",
            )
        for block in unit["blocks"]:
            if block.get("kind") == "text" and id(block) not in touched:
                paragraphs = block.get("paragraphs", [])
                if len(paragraphs) >= 2 and "dense_section" not in planted:
                    probe = " ".join(paragraphs)
                    block["paragraphs"] = [probe]
                    touched.add(id(block))
                    planted["dense_section"] = {
                        "defect": "dense_section",
                        "check": CHECKS["dense_section"],
                        "dimension": "cognitive_load",
                        "item": f"study/{unit['key']}",
                        "probe": probe,
                    }
            if block.get("kind") == "derivation":
                for group in block["groups"]:
                    for line in group["lines"]:
                        replace("missing_reason", unit, line, "reason", "This step is allowed.")
            if block.get("kind") == "figure":
                replace("repeated_caption", unit, block, "caption", block["alt"])
    return list(planted.values())


def _findings(project: Path) -> list[tuple[str, dict]]:
    card = _read(project / ".tum-mcp" / "review.json") or {}
    return [
        (review["item"], finding)
        for review in card.get("reviews", [])
        for finding in review.get("findings", [])
    ]


def plant(workspace: Path) -> dict:
    """Plants every defect the course has a place for; returns what was planted where and the
    findings the scorecard already held, which do not count as finding a planted defect."""
    project = _project(workspace)
    app = project / "app"
    content, exam = _read(app / "content.json"), _read(app / "exam.json")
    if content is None:
        raise LabError("Calibration needs Study content to plant defects in.")
    planted, touched = [], set()
    for name, (dimension, apply, _undone) in DEFECTS.items():
        if record := apply(content, exam, touched):
            planted.append(
                {"defect": name, "check": CHECKS[name], "dimension": dimension, **record}
            )
    planted.extend(_extra_defects(content, touched))
    (app / "content.json").write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n")
    if exam is not None:
        (app / "exam.json").write_text(json.dumps(exam, indent=2, ensure_ascii=False) + "\n")
    prior = [
        [item, finding["dimension"], finding.get("note", "")]
        for item, finding in _findings(project)
    ]
    return {"defects": planted, "prior": prior}


def recall(workspace: Path, planted: dict) -> dict:
    """Which planted defects the review found (a new finding on the item and dimension) or
    undid, the recall per dimension, and how many new findings were rejected."""
    project = _project(workspace)
    prior = {tuple(entry) for entry in planted["prior"]}
    findings = [
        (item, finding)
        for item, finding in _findings(project)
        if (item, finding["dimension"], finding.get("note", "")) not in prior
    ]
    content = _read(project / "app" / "content.json") or {"units": []}
    text = "\n".join(
        (project / "app" / name).read_text(encoding="utf-8")
        for name in ("content.json", "exam.json")
        if (project / "app" / name).is_file()
    )
    results, by_dimension = [], {}
    for defect in planted["defects"]:
        noted = any(
            item == defect["item"]
            and finding["dimension"] == defect["dimension"]
            and finding.get("check") == CHECKS[defect["defect"]]
            and finding.get("status", "accepted") == "accepted"
            for item, finding in findings
        )
        undone = DEFECTS[defect["defect"]][2] if defect["defect"] in DEFECTS else _probe_gone
        fixed = undone(text, content, defect)
        found = noted or fixed
        results.append({**defect, "found": found, "noted": noted, "fixed": fixed})
        counts = by_dimension.setdefault(defect["dimension"], [0, 0])
        counts[0] += found
        counts[1] += 1
    rejected = sum(finding.get("status") == "rejected" for _, finding in findings)
    return {
        "defects": results,
        "recall": {name: f"{found}/{total}" for name, (found, total) in by_dimension.items()},
        "found": sum(item["found"] for item in results),
        "planted": len(results),
        "findings": len(findings),
        "rejected": rejected,
        "rejected_share": rejected / len(findings) if findings else None,
    }
