import json
from pathlib import Path

import pytest
from documents import content_file
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.review import loop
from tum_mcp.course.review.media import media_reviews_name
from tum_mcp.course.review.models import CRITERIA, SHEET


def report(project: Path) -> dict:
    result = CliRunner().invoke(app, ["study", "report", str(project), "--section", "review"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["review"]


def score_media(project: Path, reviews: list[dict]) -> None:
    path = project / media_reviews_name()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reviews), encoding="utf-8")


def course_blocks(project: Path) -> dict:
    return loop.load(project).items["course"].blocks


def test_course_memory_relations_stale_the_course_without_resetting_progress(
    tmp_path: Path, course_memory: Path
) -> None:
    from knowledge_annotations import annotation, write_registry
    from knowledge_fixture import knowledge_project

    from tum_mcp.course.content.exam import concept_revision
    from tum_mcp.course.content.exam_data import read_exam
    from tum_mcp.course.project.store import private_path

    root = knowledge_project(tmp_path)
    native = course_blocks(root)["structure"]
    write_registry(root, [annotation(root, "exam/concept/observer")], reviewed=True)
    active = course_blocks(root)
    assert active["structure"] == native and "knowledge" in active
    progress = concept_revision(read_exam(root).concepts[0])
    path = content_file(root, "exam")
    value = json.loads(path.read_bytes())
    value["concepts"][0]["details"][0]["title"] = "Revised meaning"
    path.write_text(json.dumps(value))
    changed = course_blocks(root)
    assert changed["structure"] == native and changed["knowledge"] != active["knowledge"]
    assert concept_revision(read_exam(root).concepts[0]) == progress
    private_path(root, "knowledge.json").unlink()
    assert course_blocks(root) == {"structure": native}


def test_malformed_sidecar_blocks_semantic_report_but_not_local_build(
    tmp_path: Path, course_memory: Path
) -> None:
    from knowledge_fixture import knowledge_project

    from tum_mcp.course.app.build import build
    from tum_mcp.course.project.store import private_path

    root = knowledge_project(tmp_path)
    private_path(root, "knowledge.json").write_text("{PRIVATE_SENTINEL")
    result = CliRunner().invoke(app, ["study", "report", str(root), "--section", "structure"])
    assert result.exit_code != 0 and "PRIVATE_SENTINEL" not in str(result.exception)
    build(root, publish=False)


def test_the_cheatsheet_and_each_pattern_are_reviewed_items(tmp_path: Path) -> None:
    from knowledge_fixture import knowledge_project

    root = knowledge_project(tmp_path, workspaces=frozenset({"exam"}))
    items = loop.load(root).items
    assert items[SHEET].profile == "exam-sheet"
    patterns = [key for key, item in items.items() if item.profile == "exam-pattern"]
    assert patterns
    before = items[SHEET].blocks
    path = content_file(root, "exam")
    value = json.loads(path.read_bytes())
    value["concepts"][0]["line"] = value["concepts"][0]["line"] + " Revised."
    path.write_text(json.dumps(value))
    assert loop.load(root).items[SHEET].blocks != before


def test_every_native_solution_transfer_compare_and_explore_visual_can_be_scored(tmp_path: Path):
    from knowledge_fixture import knowledge_project

    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.app.visuals import visual_ids
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.content.exercises import SolutionAnswer, TransferTask
    from tum_mcp.course.content.responses import SelfCheck
    from tum_mcp.course.content.study import TableBlock
    from tum_mcp.course.review.models import VisualReview

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
    first = report(project)
    item = first["media"]["items"][0]
    review = media_review(project, item)
    score_media(project, [review | {"evidence": []}])
    missing = report(project)["media"]
    assert set(missing["unscored_dimensions"][0]["dimensions"]) == set(item["required_dimensions"])
    assert not missing["passed"]
    score_media(project, [review])
    assert report(project)["media"]["passed"]
    # A gap is not filled by a timestamped note elsewhere in the same file.
    listening = review["evidence"][-1]
    listening["intervals"] = [{"start": 0, "end": 0.5}, {"start": 1, "end": 2}]
    score_media(project, [review])
    assert report(project)["media"]["unscored_dimensions"][0]["dimensions"] == ["delivery"]
    listening["intervals"] = [{"start": 0, "end": 1}, {"start": 0.9, "end": 2}]
    score_media(project, [review])
    assert report(project)["media"]["passed"]
    (project / listening["path"]).write_text("Changed observer record.", encoding="utf-8")
    assert not report(project)["media"]["passed"]


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
    score_media(media_audio, [review])
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
    score_media(media_audio, [review])
    assert report(media_audio)["media"]["passed"]
    score_media(media_audio, [review | {"evidence": review["evidence"][:-1]}])
    assert not report(media_audio)["media"]["passed"]
    review["scores"]["intuition"] = 1
    score_media(media_audio, [review])
    assert not report(media_audio)["media"]["passed"]


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

    from tum_mcp.course.media.inventory import MediaInventory, MediaItem
    from tum_mcp.course.review.media import media_report
    from tum_mcp.course.review.models import MediaReview

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


def test_media_structure_ignores_codec_bytes_but_tracks_chapter_links(media_audio: Path) -> None:
    import hashlib

    from tum_mcp.course.media.audio import AudioValidation

    original = report(media_audio)
    base = course_blocks(media_audio)["structure"]
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
    assert course_blocks(media_audio)["structure"] == base
    assert current["media"]["items"][0]["revision"] != original["media"]["items"][0]["revision"]
    chapters_path = media_audio / "audio" / receipt["chapters"]["path"]
    chapters = json.loads(chapters_path.read_bytes())
    chapters[0]["title"] = "A reorganized chapter"
    data = json.dumps(chapters).encode()
    chapters_path.write_bytes(data)
    receipt["chapters"].update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert course_blocks(media_audio)["structure"] != base
    path.write_text("{broken optional manifest", encoding="utf-8")
    broken = report(media_audio)
    assert broken["media"]["invalid"] and not broken["media"]["passed"]
