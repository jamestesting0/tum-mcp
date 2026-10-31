import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.study_review import CRITERIA, DIMENSIONS, read_scorecard, scorecard_path
from tum_mcp.study_store import load_state


def test_course_semantic_review_stales_without_resetting_native_progress(
    tmp_path: Path, course_memory: Path
) -> None:
    from knowledge_annotations import annotation, write_registry
    from knowledge_fixture import knowledge_project

    from tum_mcp.course_app_paths import app_path
    from tum_mcp.exam_content import concept_revision
    from tum_mcp.exam_data import read_exam
    from tum_mcp.study_store import private_path

    root = knowledge_project(tmp_path)
    native = report(root)["course"]["revision"]
    write_registry(root, [annotation(root, "exam/concept/observer")])
    assert report(root)["course"]["revision"] == native
    write_registry(root, [annotation(root, "exam/concept/observer")], reviewed=True)
    assert report(root)["course"]["revision"] == native
    active = report(root)["course"]["knowledge_revision"]
    score(root, [], whole(report(root)))
    assert report(root)["course"]["status"] == "fresh"
    progress = concept_revision(read_exam(root).concepts[0])
    path = app_path(root, "exam.json")
    value = json.loads(path.read_bytes())
    value["concepts"][0]["details"][0]["title"] = "Revised meaning"
    path.write_text(json.dumps(value))
    assert report(root)["course"]["revision"] == native
    stale = report(root)["course"]["knowledge_revision"]
    assert stale != active
    assert report(root)["course"]["status"] == "stale"
    assert concept_revision(read_exam(root).concepts[0]) == progress
    private_path(root, "knowledge.json").unlink()
    assert report(root)["course"]["revision"] == native


def test_malformed_sidecar_blocks_semantic_report_but_not_local_build(
    tmp_path: Path, course_memory: Path
) -> None:
    from knowledge_fixture import knowledge_project

    from tum_mcp.study_build import build
    from tum_mcp.study_store import private_path

    root = knowledge_project(tmp_path)
    private_path(root, "knowledge.json").write_text("{PRIVATE_SENTINEL")
    result = CliRunner().invoke(app, ["study", "report", str(root), "--section", "structure"])
    assert result.exit_code != 0 and "PRIVATE_SENTINEL" not in str(result.exception)
    build(root, publish=False)


def report(project: Path) -> dict:
    result = CliRunner().invoke(app, ["study", "report", str(project), "--section", "review"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["review"]


def score(project: Path, reviews: list[dict], course: dict | None = None) -> None:
    card = {"course_key": load_state(project).course.key, "reviews": reviews}
    scorecard_path(project).write_text(
        json.dumps(card | ({"course": course} if course else {})), encoding="utf-8"
    )


def whole(review: dict) -> dict:
    """A course review that scores every dimension the report lists at 3."""
    course = review["course"]
    scores = {name: 3 for name in course["dimensions"]}
    return {"revision": course["revision"], "reviewed_at": "2026-10-30", "scores": scores} | (
        {"knowledge_revision": course["knowledge_revision"]}
        if "knowledge_revision" in course
        else {}
    )


def reviewed(project: Path) -> list[dict]:
    """Every unit and exercise scored 3 on every dimension and visual."""
    listed = report(project)["unreviewed"]
    return [
        {
            "item": entry["item"],
            "revision": entry["revision"],
            "reviewed_at": "2026-10-30",
            "scores": {name: 3 for name in DIMENSIONS},
            "visuals": [
                {"visual": key, "scores": {name: 3 for name in CRITERIA}}
                for key in entry["visuals"]
            ],
        }
        for entry in listed
    ]


def test_every_native_solution_transfer_compare_and_explore_visual_can_be_scored(tmp_path: Path):
    from knowledge_fixture import knowledge_project

    from tum_mcp.exercise_checks import SelfCheck
    from tum_mcp.exercise_content import SolutionAnswer, TransferTask
    from tum_mcp.exercise_data import read_exercises
    from tum_mcp.study_build import read_content
    from tum_mcp.study_content import TableBlock
    from tum_mcp.study_review import VisualReview
    from tum_mcp.study_visuals import visual_ids

    root = knowledge_project(tmp_path, workspaces=frozenset({"study", "exercises"}))
    content, exercises = read_content(root), read_exercises(root)
    unit, group = content.units[0], exercises.sets[0]
    exercise = group.exercises[0]
    table = TableBlock(
        kind="table",
        columns=("State", "Cost"),
        rows=(("A", "0"),),
        caption="Synthetic trace",
        sources=(unit.sources[0].key,),
        pages="1",
    )
    content = content.model_copy(
        update={
            "units": (
                unit.model_copy(
                    update={"explore": (unit.explore[0].model_copy(update={"blocks": (table,)}),)}
                ),
                *content.units[1:],
            )
        }
    )
    exercise = exercise.model_copy(
        update={
            "solution": exercise.solution.model_copy(
                update={"answers": (SolutionAnswer(blocks=(table,)),)}
            ),
            "transfer": TransferTask(prompt="Change one edge cost.", answer=(table,)),
            "steps": (
                exercise.steps[0].model_copy(
                    update={
                        "check": SelfCheck(
                            kind="self_check",
                            rubric=("Compare accumulated costs.",),
                            model_answer=(table,),
                        )
                    }
                ),
            ),
        }
    )
    exercises = exercises.model_copy(
        update={"sets": (group.model_copy(update={"exercises": (exercise,)}),)}
    )
    keys = {key for values in visual_ids(content, exercises).values() for key in values}
    assert {"solution", "transfer", "compare", "explore"} <= {key.split(":")[0] for key in keys}

    scored = [VisualReview(visual=key, scores={name: 3 for name in CRITERIA}) for key in keys]

    assert {item.visual for item in scored} == keys


def test_scores_follow_the_content_they_read_and_low_scores_need_a_fix(
    exercise_project: Path,
) -> None:
    # Given a course with no review yet, every unit and exercise is listed with its revision.
    project = exercise_project
    first = report(project)
    assert first["scorecard"] is False and first["passed"] is False
    listed = {entry["item"]: entry for entry in first["unreviewed"]}
    items = {key: entry["revision"] for key, entry in listed.items()}
    assert any(key.startswith("study/") for key in items)
    assert any(key.startswith("exercises/") for key in items)
    # Each listed item names the visuals the contact sheets show, which need their own scores.
    drawn = next(key for key, entry in listed.items() if entry["visuals"])
    sharp = {name: 3 for name in CRITERIA}
    good = {name: 3 for name in DIMENSIONS}
    reviews = [
        {"item": key, "revision": value, "reviewed_at": "2026-10-29", "scores": good}
        for key, value in items.items()
    ]
    score(project, reviews)
    unscored = report(project)
    assert unscored["passed"] is False
    assert {"item": drawn, "visuals": listed[drawn]["visuals"]} in unscored["unscored_visuals"]
    for review in reviews:
        review["visuals"] = [
            {"visual": key, "scores": sharp} for key in listed[review["item"]]["visuals"]
        ]
    # When every item and visual scores 3, only the course review is missing; then it passes.
    score(project, reviews)
    assert report(project)["course"]["status"] == "unreviewed"
    assert report(project)["passed"] is False
    course = whole(report(project))
    score(project, reviews, course)
    assert report(project)["passed"] is True
    # A weak visual needs a note and caps the item's representation score.
    index = next(i for i, review in enumerate(reviews) if review["item"] == drawn)
    weak = dict(reviews[index], visuals=[dict(reviews[index]["visuals"][0])])
    weak["visuals"][0]["scores"] = sharp | {"legibility": 2}
    score(project, [*reviews[:index], weak, *reviews[index + 1 :]], course)
    with pytest.raises(CampusError, match="note names what is wrong"):
        read_scorecard(project)
    weak["visuals"][0]["note"] = "On a phone the edge labels shrink below 12 px."
    score(project, [*reviews[:index], weak, *reviews[index + 1 :]], course)
    with pytest.raises(CampusError, match="weakest visual"):
        read_scorecard(project)
    score(project, reviews, course)
    # A score below 3 must name what the student meets.
    unit = next(key for key in items if key.startswith("study/"))
    reviews[0] = reviews[0] | {"scores": good | {"cognitive_load": 2}}
    score(project, reviews, course)
    with pytest.raises(CampusError, match="names its finding"):
        read_scorecard(project)
    finding = {"dimension": "cognitive_load", "note": "Three ideas in one paragraph."}
    reviews[0] |= {"findings": [finding]}
    score(project, reviews, course)
    low = report(project)
    assert low["passed"] is False and low["below_bar"][0]["scores"] == {"cognitive_load": 2}
    # A friction kept for a stated reason passes; an item that blocks learning never does.
    reviews[0] |= {"kept": "The source gives no smaller example."}
    score(project, reviews, course)
    assert report(project)["passed"] is True
    reviews[0] |= {"scores": good | {"cognitive_load": 1}}
    score(project, reviews, course)
    assert report(project)["passed"] is False
    # Editing a reviewed unit makes its review stale.
    reviews[0] = {**reviews[0], "scores": good, "findings": []}
    reviews[0].pop("kept")
    score(project, reviews, course)
    content_path = project / "study/content.json"
    content = json.loads(content_path.read_bytes())
    target = next(u for u in content["units"] if f"study/{u['key']}" == unit)
    target["summary"] += " Revised."
    content_path.write_text(json.dumps(content), encoding="utf-8")
    stale = report(project)
    assert [entry["item"] for entry in stale["stale"]] == [unit] and stale["passed"] is False


def test_older_reviews_still_load_and_the_course_review_follows_the_outline(
    exercise_project: Path,
) -> None:
    # Given a scorecard saved before intuition, organization and redundancy were scored.
    project = exercise_project
    reviews = reviewed(project)
    later = {"intuition", "organization", "redundancy"}
    older = [r | {"scores": {n: 3 for n in DIMENSIONS if n not in later}} for r in reviews]
    score(project, older)
    # When the report reads it, nothing breaks: each item lists only the missing dimensions.
    first = report(project)
    assert first["unreviewed"] == [] and first["stale"] == [] and first["passed"] is False
    assert {tuple(entry["dimensions"]) for entry in first["unscored_dimensions"]} == {
        ("intuition", "organization", "redundancy")
    }
    # A review saved with no scores at all lists every dimension instead of failing.
    score(project, [reviews[0] | {"scores": {}}, *older[1:]])
    empty = report(project)
    assert empty["passed"] is False
    assert {"item": reviews[0]["item"], "dimensions": list(DIMENSIONS)} in empty[
        "unscored_dimensions"
    ]
    # Study and Exercises are both prepared, so the course review also scores integration.
    course = first["course"]
    assert course["workspaces"] == ["study", "exercises"] and "integration" in course["dimensions"]
    partial = whole(first)
    partial["scores"].pop("integration")
    score(project, reviews, partial)
    assert report(project)["course"]["unscored"] == ["integration"]
    # A check id belongs to the dimension of its finding.
    linked = whole(first) | {
        "scores": whole(first)["scores"] | {"integration": 2},
        "findings": [
            {
                "dimension": "integration",
                "check": "redundancy.one_home",
                "note": "sample-minimum-proof links no Study passage.",
            }
        ],
    }
    score(project, reviews, linked)
    with pytest.raises(CampusError, match="another dimension"):
        read_scorecard(project)
    linked["findings"][0]["check"] = "integration.prerequisite_links"
    score(project, reviews, linked)
    low = report(project)
    assert low["passed"] is False and low["course"]["below_bar"]["scores"] == {"integration": 2}
    assert low["failed_checks"] == {"integration.prerequisite_links": 1}
    score(project, reviews, whole(first))
    assert report(project)["passed"] is True
    # Rewording a unit leaves the course review fresh; reordering units makes it stale.
    content_path = project / "study/content.json"
    content = json.loads(content_path.read_bytes())
    content["units"][0]["summary"] += " Revised."
    content_path.write_text(json.dumps(content), encoding="utf-8")
    assert report(project)["course"]["status"] == "fresh"
    content["units"][:2] = content["units"][1::-1]
    content_path.write_text(json.dumps(content), encoding="utf-8")
    assert report(project)["course"]["status"] == "stale"


def test_every_solution_transfer_compare_and_explore_visual_id_can_be_scored() -> None:
    from importlib.resources import files

    from tum_mcp.exercise_checks import SelfCheck
    from tum_mcp.exercise_content import ExerciseContent, SolutionAnswer, TransferTask
    from tum_mcp.study_content import StudyContent, TableBlock
    from tum_mcp.study_review import VisualReview
    from tum_mcp.study_visuals import visual_ids

    example = files("tum_mcp") / "bundled/course_app/example"
    content = StudyContent.model_validate_json((example / "content.json").read_bytes())
    exercises = ExerciseContent.model_validate_json((example / "exercises.json").read_bytes())
    unit = next(unit for unit in content.units if unit.explore)
    group = exercises.sets[0]
    exercise = group.exercises[0]
    table = TableBlock(
        kind="table",
        columns=("State", "Cost"),
        rows=(("A", "0"),),
        caption="Synthetic trace",
        sources=(unit.explore[0].sources[0].key,),
        pages="1",
    )
    content = content.model_copy(
        update={
            "units": tuple(
                item.model_copy(
                    update={"explore": (item.explore[0].model_copy(update={"blocks": (table,)}),)}
                )
                if item.key == unit.key
                else item
                for item in content.units
            )
        }
    )
    answer = table.model_copy(update={"sources": (exercise.sources[0].key,)})
    exercise = exercise.model_copy(
        update={
            "solution": exercise.solution.model_copy(
                update={"answers": (SolutionAnswer(blocks=(answer,)),)}
            ),
            "transfer": TransferTask(prompt="Change one edge cost.", answer=(answer,)),
            "steps": (
                exercise.steps[0].model_copy(
                    update={
                        "check": SelfCheck(
                            kind="self_check",
                            rubric=("Compare accumulated costs.",),
                            model_answer=(answer,),
                        )
                    }
                ),
            ),
        }
    )
    exercises = exercises.model_copy(
        update={"sets": (group.model_copy(update={"exercises": (exercise,)}),)}
    )
    keys = {key for values in visual_ids(content, exercises).values() for key in values}
    assert {"solution", "transfer", "compare", "explore"} <= {key.split(":")[0] for key in keys}
    # Every emitted id is accepted unchanged, and a malformed one is still rejected.
    scored = [VisualReview(visual=key, scores={name: 3 for name in CRITERIA}) for key in keys]
    assert {item.visual for item in scored} == keys
    with pytest.raises(ValueError):
        VisualReview(visual="answer:2", scores={name: 3 for name in CRITERIA})
