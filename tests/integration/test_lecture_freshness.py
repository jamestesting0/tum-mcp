import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from tum_mcp.errors import CampusError
from tum_mcp.lecture_evidence import Interval, Recording
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.receipts import InvalidReceipt, PreparedReceipt, source_text
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate
from tum_mcp.lecture_processing.visuals import SourceFrame
from tum_mcp.study_build import build
from tum_mcp.study_models import Binding, Course, Coverage, Resource, Snapshot
from tum_mcp.study_store import digest
from tum_mcp.study_sync import sync


@pytest.mark.parametrize("failure", ["whole_silence", "invented_frame", "generated_diagram"])
def test_invalid_recording_or_frame_blocks_new_build_before_source_sync(
    tmp_path: Path, failure: str, lecture_extension: Path
) -> None:
    # Synthetic data with a realistic provider binding; this test performs no campus reads.
    recording = Recording(
        course_slug="synthetic-fixture",
        course_id=42,
        recording_id=11,
        recorded_on="2026-10-25",
        duration_s=600,
    )
    valid = evaluate(RecordingTiming(duration_s=600))
    receipt = PreparedReceipt(
        status="prepared",
        key=recording.key,
        recording=recording,
        title="Synthetic provider fixture",
        checked_at="2026-10-26T10:00:00Z",
        validity=valid,
        source_revision="a" * 64,
        metadata_revision="b" * 64,
        processed=(Interval(start_s=0, end_s=600),),
        missing=(),
        transcript_sha256="c" * 64,
        frames_sha256="d" * 64,
        bytes_downloaded=0,
        media_reused=0,
        chunks_reused=0,
        inference_s=0,
    )
    text = source_text(receipt)
    snapshot = Snapshot(
        schema_version=2,
        course=Course(
            key="receipt-fixture",
            title="Synthetic provider fixture",
            semester="winter",
            bindings=(
                Binding(
                    key="live", provider="tum_live", course_id="42", course_slug="synthetic-fixture"
                ),
            ),
        ),
        coverage=(Coverage(binding="live", status="partial", checked_at=receipt.checked_at),),
        resources=(
            Resource(
                key=recording.key,
                binding="live",
                kind="content",
                title=receipt.title,
                url="https://live.rbg.tum.de/w/synthetic-fixture/11",
                text=text,
            ),
        ),
    )
    incoming = tmp_path / "snapshot.json"
    incoming.write_text(snapshot.model_dump_json())
    root = tmp_path / "project"
    sync(root, incoming, course_input=snapshot.course.title)
    prepared = root / ".tum-mcp/lectures" / recording.key
    prepared.mkdir(parents=True)
    (prepared / "receipt.json").write_text(receipt.model_dump_json())
    fixtures = Path(__file__).parents[1] / "fixtures/course_app"
    notes = json.loads((fixtures / "lectures.json").read_text())
    notes["course_key"] = snapshot.course.key
    lecture = notes["lectures"][0]
    lecture["recording"] = recording.model_dump(mode="json")
    lecture["sources"] = [{"key": recording.key, "sha256": digest(text.encode())}]
    for section in lecture["sections"]:
        for block in section["blocks"]:
            block["sources"] = [recording.key]
    for evidence in notes["evidence"]:
        evidence.update(
            source_key=recording.key, source_sha256=digest(text.encode()), recording_id=11
        )
    (root / "app").mkdir()
    path = root / "app/lectures.json"
    path.write_text(json.dumps(notes))
    shutil.copytree(fixtures / "lecture-assets", root / ".tum-mcp/lecture-assets")
    figure = lecture["sections"][0]["figures"][0]
    frame_path = prepared / "frames" / Path(figure["asset"]).name
    frame_path.parent.mkdir()
    shutil.copy2(root / ".tum-mcp" / figure["asset"], frame_path)
    frame = SourceFrame(
        path=frame_path,
        sha256=figure["sha256"],
        original_sha256=figure["sha256"],
        width=figure["width"],
        height=figure["height"],
        captured_at_s=figure["captured_at_s"],
        decoded_pts_s=37.5,
    )
    frames = FrameInventory(captured=(frame,)).model_dump_json().encode()
    (prepared / "frames.json").write_bytes(frames)
    receipt = receipt.model_copy(update={"frames_sha256": digest(frames)})
    (prepared / "receipt.json").write_text(receipt.model_dump_json())
    build(root, publish=False)
    previous = (root / "app/data.mjs").read_bytes()
    invalid = InvalidReceipt(
        key=recording.key,
        course_id=42,
        recording_id=11,
        checked_at="2026-10-26T11:00:00Z",
        reason="whole_recording_silence",
        duration_s=600,
    )
    if failure == "whole_silence":
        (prepared / "receipt.json").write_text(invalid.model_dump_json())
    elif failure == "invented_frame":
        figure["captured_at_s"] = 37.55
        path.write_text(json.dumps(notes))
    else:
        forged = tmp_path / "generated.png"
        with Image.new("RGB", (640, 360), "red") as image:
            image.save(forged)
        figure["sha256"] = digest(forged.read_bytes())
        figure["asset"] = f"lecture-assets/{figure['sha256']}.png"
        shutil.copy2(forged, root / ".tum-mcp" / figure["asset"])
        path.write_text(json.dumps(notes))
    # The ordinary source inventory remains unchanged, but the latest private validity wins.
    with pytest.raises(CampusError):
        build(root, publish=False)
    assert (root / "app/data.mjs").read_bytes() == previous
    assert json.loads(path.read_text()) == notes
