import io
import json
from pathlib import Path

import pytest
from lecture_prepared_fixture import Prepared, prepare_recording
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.lecture_evidence import Interval
from tum_mcp.study_build import build


def frame_png() -> bytes:
    with Image.new("RGB", (1920, 1080), (248, 247, 243)) as image:
        ImageDraw.Draw(image).rectangle((200, 200, 1720, 880), outline=(20, 20, 20), width=8)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


@pytest.fixture
def prepared(tmp_path: Path, lecture_extension: Path) -> Prepared:
    return prepare_recording(tmp_path)


def run(*args: str):
    return CliRunner().invoke(app, ["lecture", *args])


@pytest.mark.parametrize("crop,size", [("", (960, 540)), ("0,0,960,1080", (853, 960))])
def test_thumbnail_stages_a_bounded_frame_that_the_build_verifies(
    prepared: Prepared, crop: str, size: tuple[int, int]
) -> None:
    prepared.add_frame(frame_png(), (1920, 1080), 30.0)
    args = ["thumbnail", str(prepared.root), "--recording", prepared.recording.key, "--at", "30"]
    result = run(*args, *(["--crop", crop] if crop else []))
    assert result.exit_code == 0, result.output
    staged = json.loads(result.output)
    thumbnail, evidence = staged["thumbnail"], staged["evidence"]
    with Image.open(prepared.root / ".tum-mcp" / thumbnail["asset"]) as image:
        assert image.size == size == (thumbnail["width"], thumbnail["height"])
    assert evidence["kind"] == "frame" and evidence["recording_id"] == 11
    window = Interval.model_validate(evidence["interval"])
    assert window.start_s <= thumbnail["captured_at_s"] <= window.end_s
    # Pasting the printed objects, with a key and review, is all the author does.
    highlight = prepared.notes["lectures"][0]["highlights"][0]
    highlight["thumbnail"] = thumbnail | {"evidence": "board"}
    board = next(item for item in prepared.notes["evidence"] if item["key"] == "board")
    board.update(evidence | {"key": "board", "reviewed": True})
    prepared.write_notes()
    build(prepared.root, publish=False)
    assert (prepared.root / "app" / thumbnail["asset"]).is_file()


def test_thumbnail_without_a_capture_names_the_prepare_step(prepared: Prepared) -> None:
    before = sorted((prepared.root / ".tum-mcp/lecture-assets").iterdir())
    args = ["thumbnail", str(prepared.root), "--recording", prepared.recording.key, "--at", "99"]
    result = run(*args)
    assert result.exit_code != 0 and "--frame-at 99" in str(result.exception)
    assert sorted((prepared.root / ".tum-mcp/lecture-assets").iterdir()) == before


def check(prepared: Prepared):
    result = run("check", str(prepared.root))
    return result, json.loads(result.output)


def test_check_reports_aligned_highlights_with_their_opening_and_closing_speech(
    prepared: Prepared,
) -> None:
    result, report = check(prepared)
    assert result.exit_code == 0 and report["errors"] == 0
    lecture = report["lectures"][0]
    assert (lecture["highlights"], lecture["highlight_s"], lecture["share"]) == (2, 100.0, 0.17)
    first = lecture["items"][0]
    assert first["issues"] == [] and first["duration_s"] == 40
    assert first["opening"].startswith("Why does the first discovery")
    assert first["closing"].endswith("distances d and d plus one.")
    assert lecture["notes"] == 1
    assert lecture["note_items"][0]["issues"] == []
    assert "both endpoints" in lecture["note_items"][0]["speech"]


def test_check_fails_on_a_boundary_inside_a_passage(prepared: Prepared) -> None:
    highlight = prepared.notes["lectures"][0]["highlights"][0]
    highlight["interval"]["start_s"] = 23
    next(item for item in prepared.notes["evidence"] if item["key"] == "speech")["interval"][
        "start_s"
    ] = 23
    prepared.write_notes()
    result, report = check(prepared)
    assert result.exit_code == 1 and report["errors"] == 1
    assert report["lectures"][0]["items"][0]["issues"] == ["start_off_passage"]


def test_check_warns_about_unclear_speech_without_failing(prepared: Prepared) -> None:
    unclear = (Interval(start_s=130, end_s=140),)
    prepared.write_receipt(
        prepared.receipt().model_copy(update={"status": "partial", "uncertain": unclear})
    )
    result, report = check(prepared)
    assert result.exit_code == 0 and report["errors"] == 0
    assert report["lectures"][0]["items"][1]["issues"] == ["uncertain_speech"]


def test_check_skips_transcript_review_for_synthetic_lectures(prepared: Prepared) -> None:
    prepared.notes["lectures"][0]["recording"]["synthetic"] = True
    prepared.write_notes()
    result, report = check(prepared)
    assert result.exit_code == 0
    assert report["lectures"] == [{"key": "bfs-lecture", "transcript": "synthetic"}]


def test_notes_only_build_needs_no_frames_and_check_does_not_impose_clip_boundaries(
    prepared: Prepared,
) -> None:
    lecture = prepared.notes["lectures"][0]
    lecture["highlights"] = []
    prepared.notes["evidence"] = [
        item for item in prepared.notes["evidence"] if item["key"] == "speech-note"
    ]
    prepared.notes["evidence"][0]["interval"] = {"start_s": 302.5, "end_s": 309}
    (prepared.folder / "frames.json").unlink()
    prepared.write_notes()
    result, report = check(prepared)
    assert result.exit_code == 0 and report["errors"] == 0
    assert report["lectures"][0]["highlights"] == 0
    assert report["lectures"][0]["highlight_s"] == 0
    assert report["lectures"][0]["note_items"][0]["issues"] == []
    build(prepared.root, publish=False)
    assert not (prepared.root / "app/lecture-assets").exists()


def test_note_image_must_match_its_measured_prepared_frame(prepared: Prepared) -> None:
    lecture = prepared.notes["lectures"][0]
    first, second = lecture["highlights"]
    image = first["thumbnail"] | {
        "sha256": second["thumbnail"]["sha256"],
        "asset": second["thumbnail"]["asset"],
        "alt": "The queue before the next discovery.",
    }
    lecture["notes"][0].update(image=image, evidence=["speech-note", *first["evidence"]])
    lecture["highlights"] = []
    used = set(lecture["notes"][0]["evidence"])
    prepared.notes["evidence"] = [
        item for item in prepared.notes["evidence"] if item["key"] in used
    ]
    prepared.write_notes()
    with pytest.raises(CampusError, match="prepared recording capture"):
        build(prepared.root, publish=False)
