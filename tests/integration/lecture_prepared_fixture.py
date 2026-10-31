"""A synced course with one prepared synthetic recording: transcript, frames and highlights."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from tum_mcp.lecture_evidence import Interval, Recording
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.receipts import PreparedReceipt, source_text
from tum_mcp.lecture_processing.transcript_models import Passage
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate
from tum_mcp.lecture_processing.visuals import SourceFrame
from tum_mcp.study_models import Binding, Course, Coverage, Resource, Snapshot
from tum_mcp.study_store import digest
from tum_mcp.study_sync import sync

FIXTURES = Path(__file__).parents[1] / "fixtures/course_app"
SPEECH = (
    (0, 20, "Welcome back."),
    (20, 40, "Why does the first discovery give a shortest path?"),
    (40, 60, "Because the queue only holds distances d and d plus one."),
    (60, 120, "A short aside about the homework."),
    (120, 150, "Mark a vertex when you put it into the queue."),
    (150, 180, "Otherwise it enters once per incoming edge."),
    (180, 300, "The rest of the lecture covers depth-first search."),
    (300, 310, "Count an undirected edge in both endpoints' adjacency lists."),
    (310, 600, "We continue with depth-first search."),
)


@dataclass(frozen=True)
class Prepared:
    root: Path
    recording: Recording
    folder: Path
    notes_path: Path
    notes: dict

    def receipt(self) -> PreparedReceipt:
        return PreparedReceipt.model_validate_json((self.folder / "receipt.json").read_bytes())

    def write_receipt(self, receipt: PreparedReceipt) -> None:
        (self.folder / "receipt.json").write_text(receipt.model_dump_json())

    def write_notes(self) -> None:
        self.notes_path.write_text(json.dumps(self.notes))

    def add_frame(self, payload: bytes, size: tuple[int, int], at: float) -> SourceFrame:
        """Record a measured capture requested at `at`, as lecture prepare --frame-at does."""
        sha = digest(payload)
        path = self.folder / "frames" / f"{sha}.png"
        path.write_bytes(payload)
        frame = SourceFrame(
            path=path,
            sha256=sha,
            original_sha256=sha,
            width=size[0],
            height=size[1],
            captured_at_s=at + 0.033,
            decoded_pts_s=at + 0.033,
            requested_at_s=at,
        )
        inventory = FrameInventory.model_validate_json((self.folder / "frames.json").read_bytes())
        self._write_frames(inventory.captured + (frame,))
        return frame

    def _write_frames(self, frames: tuple[SourceFrame, ...]) -> None:
        payload = FrameInventory(captured=frames).model_dump_json().encode()
        (self.folder / "frames.json").write_bytes(payload)
        self.write_receipt(self.receipt().model_copy(update={"frames_sha256": digest(payload)}))


def prepare_recording(tmp_path: Path) -> Prepared:
    # Synthetic data with a realistic provider binding; nothing here reads the campus.
    recording = Recording(
        course_slug="synthetic-fixture",
        course_id=42,
        recording_id=11,
        recorded_on="2026-10-25",
        duration_s=600,
    )
    transcript = (
        b"["
        + b",".join(
            Passage(interval=Interval(start_s=start, end_s=end), text=text, origin="subtitle")
            .model_dump_json()
            .encode()
            for start, end, text in SPEECH
        )
        + b"]"
    )
    receipt = PreparedReceipt(
        status="prepared",
        key=recording.key,
        recording=recording,
        title="Synthetic provider fixture",
        checked_at="2026-10-26T10:00:00Z",
        validity=evaluate(RecordingTiming(duration_s=600)),
        source_revision="a" * 64,
        metadata_revision="b" * 64,
        processed=(Interval(start_s=0, end_s=600),),
        missing=(),
        transcript_sha256=digest(transcript),
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
    incoming.write_text(snapshot.model_dump_json(), encoding="utf-8")
    root = tmp_path / "project"
    sync(root, incoming, course_input=snapshot.course.title)
    folder = root / ".tum-mcp/lectures" / recording.key
    (folder / "frames").mkdir(parents=True)
    (folder / "transcript.json").write_bytes(transcript)
    notes = json.loads((FIXTURES / "lectures.json").read_text())
    notes["course_key"] = snapshot.course.key
    lecture = notes["lectures"][0]
    lecture["recording"] = recording.model_dump(mode="json")
    lecture["sources"] = [{"key": recording.key, "sha256": digest(text.encode())}]
    for entry in lecture["notes"] + lecture["highlights"]:
        entry["sources"] = []
        entry.pop("pages", None)
    for evidence in notes["evidence"]:
        evidence.update(
            source_key=recording.key, source_sha256=digest(text.encode()), recording_id=11
        )
    (root / "app").mkdir()
    shutil.copytree(FIXTURES / "lecture-assets", root / ".tum-mcp/lecture-assets")
    prepared = Prepared(root, recording, folder, root / "app/lectures.json", notes)
    prepared.write_receipt(receipt)
    prepared.write_notes()
    frames = []
    for highlight in lecture["highlights"]:
        thumbnail = highlight["thumbnail"]
        path = folder / "frames" / Path(thumbnail["asset"]).name
        shutil.copy2(root / ".tum-mcp" / thumbnail["asset"], path)
        frames.append(
            SourceFrame(
                path=path,
                sha256=thumbnail["sha256"],
                original_sha256=thumbnail["sha256"],
                width=thumbnail["width"],
                height=thumbnail["height"],
                captured_at_s=thumbnail["captured_at_s"],
                decoded_pts_s=thumbnail["captured_at_s"],
            )
        )
    prepared._write_frames(tuple(frames))
    return prepared
