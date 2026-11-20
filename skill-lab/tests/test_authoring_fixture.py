import subprocess
from array import array
from pathlib import Path
from shutil import copytree

import pytest
from pypdf import PdfReader
from skill_lab import authoring_fixture as fixture
from skill_lab.scenarios import load

from tum_mcp.course.lecture.selection import selection_progress
from tum_mcp.course.project.store import load_state
from tum_mcp.course.workflow.tasks import begin, read_task
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.receipts import PASSAGES, evidence_bytes, usable_receipt


@pytest.fixture(scope="module")
def workspaces(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    main = tmp_path_factory.mktemp("fai-journey")
    resume = tmp_path_factory.mktemp("fai-resume")
    fixture.seed(main, fixture.JOURNEY)
    fixture.seed(resume, fixture.RESUME)
    return main, resume


def test_resume_reuses_identical_sources_and_claims_paused_task(
    workspaces: tuple[Path, Path],
) -> None:
    main, resume = workspaces
    main_files = {p.relative_to(main): p.read_bytes() for p in main.rglob("*") if p.is_file()}
    assert main_files == {p: (resume / p).read_bytes() for p in main_files}
    assert not (main / "app").exists() and not (resume / "app").exists()
    receipt = usable_receipt(resume, fixture.RECORDING_KEY)
    progress = selection_progress(resume, receipt)
    assert progress.next_interval is not None
    assert (progress.next_interval.start_s, progress.next_interval.end_s) == (182, 391)
    assert {item.key for item in progress.materials} == {"lecture-5-search", "lecture-5-resolution"}
    old = read_task(resume)
    assert old is not None and old.phase == "paused"
    task = begin(resume, old.batch, owner="codex:fai-fresh-session")
    assert task.phase == "pending" and task.owner != old.owner


def test_recording_has_speech_and_frames_at_the_proof_and_correction(
    workspaces: tuple[Path, Path],
) -> None:
    main, _ = workspaces
    receipt = usable_receipt(main, fixture.RECORDING_KEY)
    assert receipt.recording.synthetic is False
    assert receipt.recording.duration_s == 399
    passages = PASSAGES.validate_json(evidence_bytes(main, receipt.key, "transcript.json"))
    assert passages[49].interval.start_s < 350 == passages[50].interval.start_s
    assert "one, not two" in passages[50].text
    assert passages[52].interval.start_s == 364
    assert passages[53].interval.start_s == 371
    frames = FrameInventory.model_validate_json(evidence_bytes(main, receipt.key, "frames.json"))
    video = main / fixture.RECORDING_FILE
    for start, at in ((350, 351), (364, 365), (371, 372)):
        audio = subprocess.check_output(
            (
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-ss",
                str(start),
                "-t",
                "2",
                "-i",
                str(video),
                "-vn",
                "-f",
                "s16le",
                "-",
            ),
            timeout=10,
        )
        assert max(abs(sample) for sample in array("h", audio)) > 1000
        decoded = subprocess.check_output(
            (
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-ss",
                str(at),
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ),
            timeout=10,
        )
        frame = next(frame for frame in frames.captured if frame.decoded_pts_s == at)
        assert (video.parent / frame.path).read_bytes() == decoded
    assert len({frame.sha256 for frame in frames.captured}) == 4


def test_edited_transcript_fails_real_evidence_read(
    workspaces: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    main, _ = workspaces
    _ = copytree(main, tmp_path, dirs_exist_ok=True)
    transcript = (tmp_path / fixture.RECORDING_FILE).with_name("transcript.json")
    _ = transcript.write_bytes(transcript.read_bytes().replace(b"one, not two", b"two, not one"))
    with pytest.raises(CampusError) as error:
        _ = evidence_bytes(tmp_path, fixture.RECORDING_KEY, "transcript.json")
    assert error.value.code == Code.STALE_RESULT


def test_clarification_is_released_only_through_controller_and_preserves_sources(
    workspaces: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    main, _ = workspaces
    _ = copytree(main, tmp_path, dirs_exist_ok=True)
    state = load_state(tmp_path)
    rule = "most recently enqueued"
    assert all(
        rule not in page.extract_text()
        for source in state.resources
        if source.path and source.path.endswith(".pdf")
        for page in PdfReader(tmp_path / source.path).pages
    )
    scenario = load(fixture.JOURNEY)
    assert len(scenario.turns) == 3 and len(load(fixture.RESUME).turns) == 1
    assert rule not in "\n".join(turn.say for turn in scenario.turns)
    assert scenario.reply_to("Which tutorial rule did you use to break ties?") is None
    assert fixture.CLARIFICATION_KEY not in {source.resource.key for source in state.resources}

    fixture.release_clarification(tmp_path)

    after = load_state(tmp_path)
    added = [source for source in after.resources if source not in state.resources]
    assert len(added) == 1 and added[0].resource.key == fixture.CLARIFICATION_KEY
    assert set(state.resources) <= set(after.resources)
    assert added[0].path is not None
    assert rule in (tmp_path / added[0].path).read_text(encoding="utf-8")
