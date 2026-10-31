import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.study_review import CRITERIA, DIMENSIONS, read_scorecard, scorecard_path
from tum_mcp.study_store import load_state


def report(project: Path) -> dict:
    result = CliRunner().invoke(app, ["study", "report", str(project), "--section", "review"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["review"]


def score(
    project: Path,
    reviews: list[dict],
    course: dict | None = None,
    media: list[dict] | None = None,
) -> None:
    card = {"course_key": load_state(project).course.key, "reviews": reviews}
    scorecard_path(project).write_text(
        json.dumps(
            card
            | ({"course": course} if course else {})
            | ({"media": media} if media is not None else {})
        ),
        encoding="utf-8",
    )


def whole(review: dict) -> dict:
    """A course review that scores every dimension the report lists at 3."""
    course = review["course"]
    scores = {name: 3 for name in course["dimensions"]}
    return {"revision": course["revision"], "reviewed_at": "2026-10-30", "scores": scores}


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


def media_review(project: Path, item: dict) -> dict:
    """Synthetic observer records exercise report mechanics, not actual perception."""
    import hashlib

    evidence = []
    for kind in (
        ("script", "signal", "listening", "frames", "playback")
        if item["modality"] == "video"
        else ("script", "signal", "listening")
    ):
        path = project / ".tum-mcp/media-review" / f"{kind}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = f"Synthetic {kind} evidence for report tests; no actual perception.".encode()
        path.write_bytes(data)
        evidence.append(
            {
                "kind": kind,
                "path": path.relative_to(project).as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "artifact_sha256": item["artifact_sha256"],
                **(
                    {"intervals": [{"start": 0, "end": item["duration"]}]}
                    if kind in {"listening", "playback"}
                    else {}
                ),
                **({"guidance_sha256": item["guidance_sha256"]} if kind == "script" else {}),
            }
        )
    return {
        "item": item["item"],
        "revision": item["revision"],
        "reviewed_at": "2026-10-31",
        "scores": {d: 3 for d in item["required_dimensions"]},
        "visuals": [{"visual": key, "scores": {c: 3 for c in CRITERIA}} for key in item["visuals"]],
        "evidence": evidence,
    }


def test_media_is_separate_and_requires_current_complete_evidence(media_audio: Path) -> None:
    project = media_audio
    reviews = reviewed(project)
    first = report(project)
    assert first["course"]["workspaces"] == ["study"]
    assert "integration" in first["course"]["dimensions"]
    item = first["media"]["items"][0]
    review = media_review(project, item)
    course = whole(first)
    score(project, reviews, course, [review | {"evidence": []}])
    missing = report(project)
    assert missing["averages"] == dict.fromkeys(DIMENSIONS, 3)
    assert missing["media"]["averages"] == {"audio": {}, "video": {}}
    assert set(missing["media"]["unscored_dimensions"][0]["dimensions"]) == set(
        item["required_dimensions"]
    )
    assert not missing["passed"]
    score(project, reviews, course, [review])
    assert report(project)["passed"]
    # A gap is not filled by a timestamped note elsewhere in the same file.
    listening = review["evidence"][-1]
    listening["intervals"] = [{"start": 0, "end": 0.5}, {"start": 1, "end": 2}]
    score(project, reviews, course, [review])
    assert report(project)["media"]["unscored_dimensions"][0]["dimensions"] == ["delivery"]
    listening["intervals"] = [{"start": 0, "end": 1}, {"start": 0.9, "end": 2}]
    score(project, reviews, course, [review])
    assert report(project)["passed"]
    evidence_path = project / listening["path"]
    evidence_path.write_text("Changed observer record.", encoding="utf-8")
    assert not report(project)["passed"]


@pytest.mark.parametrize("failure", ["artifact", "guidance", "bounds", "check", "chapter"])
def test_media_evidence_and_findings_are_source_bound(media_audio: Path, failure: str) -> None:
    item = report(media_audio)["media"]["items"][0]
    review = media_review(media_audio, item)
    match failure:
        case "artifact":
            review["evidence"][-1]["artifact_sha256"] = "0" * 64
        case "guidance":
            review["evidence"][0]["guidance_sha256"] = "0" * 64
        case "bounds":
            review["evidence"][-1]["intervals"][0]["end"] += 1
        case "check" | "chapter":
            review["scores"]["intuition"] = 2
            review["kept"] = "Synthetic source limitation."
            review["findings"] = [
                {
                    "dimension": "intuition",
                    "check": "intuition.method_choice"
                    if failure == "check"
                    else "intuition.limits",
                    "note": "Synthetic located finding.",
                    "chapter": "missing" if failure == "chapter" else "queue",
                }
            ]
    score(media_audio, reviewed(media_audio), whole(report(media_audio)), [review])
    result = report(media_audio)["media"]
    assert not result["passed"]
    assert result["invalid"] if failure in {"check", "chapter"} else result["missing_evidence"]


def test_kept_media_cannot_waive_missing_perception_or_a_blocking_score(media_audio: Path) -> None:
    review = media_review(media_audio, report(media_audio)["media"]["items"][0])
    review.update(
        scores=review["scores"] | {"intuition": 2},
        findings=[
            {
                "dimension": "intuition",
                "check": "intuition.limits",
                "note": "The source omits a boundary case.",
                "start": 0,
                "end": 1,
            }
        ],
        kept="The available source cannot establish this case; its limit is disclosed.",
    )
    reviews, course = reviewed(media_audio), whole(report(media_audio))
    score(media_audio, reviews, course, [review])
    assert report(media_audio)["passed"]
    score(media_audio, reviews, course, [review | {"evidence": review["evidence"][:-1]}])
    assert not report(media_audio)["passed"]
    review["scores"]["intuition"] = 1
    score(media_audio, reviews, course, [review])
    assert not report(media_audio)["passed"]


def test_media_structure_ignores_codec_bytes_but_tracks_chapter_links(media_audio: Path) -> None:
    import hashlib

    from tum_mcp.audio_content import AudioValidation

    original = report(media_audio)
    path = media_audio / "audio/manifest.json"
    manifest = json.loads(path.read_bytes())
    receipt = manifest["categories"]["graphs"]
    # Updating an artifact and its validation changes media review, not the course outline.
    track = media_audio / "audio" / receipt["track"]["path"]
    data = track.read_bytes() + b"\0"
    track.write_bytes(data)
    receipt["track"].update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    validation_path = media_audio / "audio" / receipt["validation"]["path"]
    validation = AudioValidation.model_validate_json(validation_path.read_bytes())
    data = (
        validation.model_copy(update={"artifact_sha256": receipt["track"]["sha256"]})
        .model_dump_json()
        .encode()
    )
    validation_path.write_bytes(data)
    receipt["validation"]["sha256"] = hashlib.sha256(data).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    current = report(media_audio)
    assert current["course"]["revision"] == original["course"]["revision"]
    assert current["media"]["items"][0]["revision"] != original["media"]["items"][0]["revision"]
    chapters_path = media_audio / "audio" / receipt["chapters"]["path"]
    chapters = json.loads(chapters_path.read_bytes())
    chapters[0]["title"] = "A reorganized chapter"
    data = json.dumps(chapters).encode()
    chapters_path.write_bytes(data)
    receipt["chapters"].update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert report(media_audio)["course"]["revision"] != original["course"]["revision"]
    path.write_text("{broken optional manifest", encoding="utf-8")
    broken = report(media_audio)
    assert broken["unreviewed"] == original["unreviewed"]
    assert broken["media"]["invalid"] and not broken["passed"]


@pytest.mark.parametrize(
    "check",
    ["intuition.method_choice", "organization.exercise_setup", "representation.answer_emphasis"],
)
def test_video_scores_need_frames_playback_and_the_actual_source_profile(
    media_audio: Path,
    check: str,
) -> None:
    from dataclasses import replace

    from pydantic import ValidationError

    from tum_mcp.study_media import MediaInventory, MediaItem
    from tum_mcp.study_media_report import media_report
    from tum_mcp.study_review import MediaReview

    item = MediaItem(
        item="video/01_worked",
        modality="video",
        profile="exercise",
        title="Synthetic worked solution",
        duration=2,
        artifact_sha256="a" * 64,
        projection={"source": "exercises/set/problem"},
        structure={"targets": ["exercises/set/problem"]},
        visuals=("c01/b01/state",),
        locations=(("c01", "b01"),),
        guidance_sha256="b" * 64,
    )
    inventory = MediaInventory(items=[item], known={item.item})
    listed = media_report(media_audio, inventory, ())["items"][0]
    review = media_review(media_audio, listed)

    def result(value: dict):
        return media_report(media_audio, inventory, (MediaReview.model_validate(value),))

    assert result(review)["passed"]
    omitted = [e for e in review["evidence"] if e["kind"] not in {"frames", "playback"}]
    missing = result(review | {"evidence": omitted})
    assert missing["unscored_dimensions"][0]["dimensions"] == [
        "representation",
        "synchronization",
    ]
    weak = json.loads(json.dumps(review))
    weak["visuals"][0].update(
        scores=dict.fromkeys(CRITERIA, 3) | {"fidelity": 1},
        note="The trace changes an unvisited vertex.",
    )
    with pytest.raises(ValidationError, match="weakest video visual"):
        result(weak)
    dimension = check.partition(".")[0]
    review["scores"][dimension] = 2
    review["findings"] = [
        {
            "dimension": dimension,
            "check": check,
            "note": "The method is named without a reason.",
            "chapter": "c01",
            "beat": "b01",
        }
    ]
    assert not result(review)["invalid"]
    inventory.items = [replace(item, profile="concept")]
    assert result(review)["invalid"][0]["review"] == [f"check_not_in_concept_profile:{check}"]


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
