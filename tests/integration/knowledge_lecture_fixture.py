"""Cached provider evidence for real-lecture integrity tests, without campus access."""

import json
from pathlib import Path

from knowledge_fixture import knowledge_project

from tum_mcp.course_app_paths import app_path
from tum_mcp.lecture_evidence import Crop, Interval, Recording
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.receipts import PreparedReceipt, source_text
from tum_mcp.lecture_processing.timeline import watch_link
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate
from tum_mcp.lecture_processing.visuals import SourceFrame, app_frame
from tum_mcp.study_store import digest, load_state, private_path


def real_cached_lecture(tmp_path: Path, *, with_frame: bool = False) -> Path:
    root = knowledge_project(tmp_path, workspaces=frozenset({"lectures"}))
    recording = Recording(
        course_slug="cached-fixture",
        course_id=42,
        recording_id=11,
        recorded_on="2026-10-25",
        duration_s=600,
    )
    cache = private_path(root, f"lectures/{recording.key}")
    cache.mkdir(parents=True, exist_ok=True)
    frames_payload = b"{}"
    figure = None
    if with_frame:
        fixtures = Path(__file__).parents[1] / "fixtures/course_app"
        figure = json.loads((fixtures / "lectures.json").read_bytes())["lectures"][0]["sections"][
            0
        ]["figures"][0]
        body = (fixtures / figure["asset"]).read_bytes()
        frame_path = cache / "frames" / f"{digest(body)}.png"
        frame_path.parent.mkdir()
        frame_path.write_bytes(body)
        frame = SourceFrame(
            path=frame_path,
            sha256=digest(body),
            original_sha256=digest(body),
            width=640,
            height=360,
            captured_at_s=37.5,
            decoded_pts_s=37.5,
        )
        frames_payload = FrameInventory(captured=(frame,)).model_dump_json().encode()
        crop = Crop(
            x=20,
            y=10,
            width=400,
            height=240,
            original_width=640,
            original_height=360,
            original_sha256=frame.sha256,
        )
        derived = app_frame(frame, root / ".tum-mcp/lecture-assets", crop)
        figure.update(
            sha256=derived.sha256,
            asset=derived.path.relative_to(root / ".tum-mcp").as_posix(),
            width=derived.width,
            height=derived.height,
            crop=crop.model_dump(mode="json"),
        )
    transcript = b"[]"
    receipt = PreparedReceipt(
        status="prepared",
        key=recording.key,
        recording=recording,
        title="Synthetic cached provider evidence",
        checked_at="2026-10-31",
        validity=evaluate(RecordingTiming(duration_s=600)),
        source_revision="a" * 64,
        metadata_revision="b" * 64,
        processed=(Interval(start_s=0, end_s=600),),
        missing=(),
        transcript_sha256=digest(transcript),
        frames_sha256=digest(frames_payload),
        bytes_downloaded=0,
        media_reused=0,
        chunks_reused=0,
        inference_s=0,
    )
    payload = source_text(receipt).encode()
    state = load_state(root).model_dump(mode="json")
    state["schema_version"] = 2
    state["course"].update(
        synthetic=False,
        bindings=[
            {
                "key": "sample",
                "provider": "tum_live",
                "course_id": "42",
                "course_slug": recording.course_slug,
            }
        ],
    )
    source = next(item for item in state["resources"] if item["resource"]["key"] == "slides")
    source["resource"]["url"] = watch_link(recording, 0).removesuffix("?t=0")
    source["sha256"] = digest(payload)
    (root / source["path"]).write_bytes(payload)
    private_path(root, "state.json").write_text(json.dumps(state), encoding="utf-8")
    path = app_path(root, "lectures.json")
    content = json.loads(path.read_bytes())
    content["lectures"][0].update(
        recording=recording.model_dump(mode="json"),
        sources=[{"key": "slides", "sha256": digest(payload)}],
    )
    if figure is not None:
        content["lectures"][0]["sections"][0]["figures"] = [figure]
    for item in content["evidence"]:
        item.update(source_sha256=digest(payload), recording_id=recording.recording_id)
    path.write_text(json.dumps(content), encoding="utf-8")
    cache = private_path(root, f"lectures/{recording.key}")
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "receipt.json").write_text(receipt.model_dump_json(), encoding="utf-8")
    (cache / "transcript.json").write_bytes(transcript)
    (cache / "frames.json").write_bytes(frames_payload)
    return root
