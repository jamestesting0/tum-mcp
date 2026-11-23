from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from tum_mcp.course.app.build import read_content
from tum_mcp.course.content.exam_data import read_exam
from tum_mcp.course.content.exercise_data import read_exercises
from tum_mcp.course.content.store import present
from tum_mcp.course.lecture.data import read_lectures
from tum_mcp.course.review import loop
from tum_mcp.errors import CampusError

if TYPE_CHECKING:
    from tum_mcp.course.checks.preparation import Readiness

ITEM_PREFIXES = ("study/", "exercises/", "exam/", "lecture/")


def learner_items(project: Path, workspace: str) -> dict[str, str]:
    """Map readable learner IDs to their corresponding readiness checks."""
    match workspace:
        case "study":
            return {
                f"study/{unit.key}": f"study/{unit.key}" for unit in read_content(project).units
            }
        case "exercises":
            content = read_exercises(project)
            return (
                {
                    f"exercises/{group.key}/{item.key}": f"exercises/{group.key}/{item.key}"
                    for group in content.sets
                    if content
                    for item in group.exercises
                }
                if content
                else {}
            )
        case "exam":
            content = read_exam(project)
            if content is None:
                return {}
            return (
                {f"exam/concept/{item.key}": "exam/sheet" for item in content.concepts}
                | {
                    f"exam/pattern/{item.key}": f"exam/pattern/{item.key}"
                    for item in content.patterns
                }
                | {
                    f"exam/mock/{mock.key}/{question.key}": f"exam/mock/{mock.key}/{question.key}"
                    for mock in content.mocks
                    for question in mock.questions
                }
            )
        case "lectures":
            from tum_mcp.course.lecture.selection import selection_item

            content = read_lectures(project)
            if content is None:
                return {}
            items = {}
            for lecture in content.lectures:
                if lecture.entries or lecture.chapters:
                    key = f"lecture/{lecture.key}"
                    items[key] = selection_item(project, lecture).key
                    items.update(
                        {f"{key}/{entry.key}": f"{key}/{entry.key}" for entry in lecture.entries}
                    )
            return items
        case _:
            raise ValueError(f"Unknown delivery workspace {workspace!r}.")


def draft_problems(readiness: Readiness, workspace: str, keys: set[str]) -> list[str]:
    """Project draft blockers onto a delivery row, including shared prerequisites."""
    workspace = "lecture" if workspace == "lectures" else workspace
    local = set(readiness.workspace_problems.get(workspace, ()))
    assigned = {problem for issues in readiness.workspace_problems.values() for problem in issues}
    return [
        problem
        for problem in dict.fromkeys((*readiness.problems, *sorted(local)))
        if any(problem.startswith((f"{key}:", f"{key}/")) for key in keys)
        or (not problem.startswith(ITEM_PREFIXES) and (problem in local or problem not in assigned))
    ]


def measure_delivery(project: Path, requested: dict[str, list[str]]) -> dict:
    rows = {}
    context = None
    draft = None
    readiness_error = ""
    if any(present(project, name) for name in requested):
        try:
            task = None
            if (project / ".tum-mcp/task.json").is_file():
                from tum_mcp.course.workflow.tasks import read_task

                task = read_task(project)
            if task and task.batch and task.review_rounds == 0:
                from tum_mcp.course.checks.batch import assess_batch

                draft = assess_batch(project, task.batch)
            else:
                context = loop.load(project)
                if state := loop.read_state(project):
                    loop.scorecard(context, state, blocked={})
        except (CampusError, OSError, ValueError, TypeError, KeyError) as error:
            context = None
            readiness_error = f"Readiness unavailable: {error}"
    for workspace, expected in requested.items():
        items: dict[str, str] = {}
        problems = []
        has_content = present(project, workspace)
        if has_content:
            try:
                items = learner_items(project, workspace)
            except (CampusError, OSError, ValueError, TypeError, KeyError) as error:
                problems.append(f"Cannot read learner items: {error}")
            if readiness_error:
                problems.append(readiness_error)
        missing = sorted(set(expected) - items.keys())
        if items:
            selected = set(expected) & items.keys() if expected else items.keys()
            keys = {items[item] for item in selected}
            if workspace == "lectures":
                keys.update(items["/".join(item.split("/")[:2])] for item in selected)
        if items and draft is not None:
            # A workspace-only request uses its batch scope when the app also has older items.
            if not expected and (scoped := keys.intersection(draft.items)):
                keys = scoped
            problems.extend(draft_problems(draft, workspace, keys))
            if draft.scope is not None:
                problems.extend(
                    f"{key}: outside the draft readiness scope"
                    for key in sorted(keys - draft.items.keys())
                )
        elif items and context is not None:
            for key in sorted(keys):
                if key not in context.items:
                    problems.append(f"{key}: readiness unavailable")
                else:
                    problems.extend(f"{key}: {problem}" for problem in loop.item_gate(context, key))
            readiness = context.preparation
            if readiness and keys.intersection(readiness.items):
                problems.extend(
                    problem
                    for problem in readiness.problems
                    if not problem.startswith(ITEM_PREFIXES)
                    or any(problem.startswith(f"{key}:") for key in keys)
                )
        status = "absent"
        if has_content:
            status = "complete" if items and not (missing or problems) else "partial"
        rows[workspace] = {
            "status": status,
            "readable_items": sorted(items),
            "missing_items": missing,
            "problems": problems,
        }
    return rows


if __name__ == "__main__":
    print(json.dumps(measure_delivery(Path(sys.argv[1]), json.load(sys.stdin))))
