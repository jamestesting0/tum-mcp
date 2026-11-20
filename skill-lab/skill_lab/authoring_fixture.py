"""Controller-only seed for the offline FAI authoring trial."""

# SIZE_OK: The fixed trial corpus and its matching evidence live in one fixture module.

from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Final, NamedTuple

from pypdf import PdfWriter
from pypdf.generic import ContentStream, DictionaryObject, NameObject

from tum_mcp.course.checks.batch import Batch
from tum_mcp.course.content.study import SourceVersion
from tum_mcp.course.lecture.evidence import Interval, Recording, SilenceMarker
from tum_mcp.course.lecture.selection import Decision, WorkingSelection
from tum_mcp.course.project.models import Binding, Course, Coverage, Kind, Resource, Snapshot
from tum_mcp.course.project.schedule import Schedule, Session
from tum_mcp.course.project.store import digest, load_state
from tum_mcp.course.project.sync import sync
from tum_mcp.course.workflow.tasks import Task
from tum_mcp.lecture_processing.receipts import PreparedReceipt, source_text
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate

from . import LabError

JOURNEY: Final = "fai-authoring-026"
RESUME: Final = "fai-authoring-026-resume"
CLARIFICATION_KEY: Final = "sheet-6-tutorial-erratum"
_RULE: Final = "For Sheet 6, Exercise 2, expand the most recently enqueued node first on equal f."
_AS_OF: Final = "2026-11-18T12:00:00Z"
_MEETINGS: Final = (date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 19))
_SOURCES: Final[tuple[tuple[str, Kind, tuple[str, ...]], ...]] = (
    (
        "lecture-5-search",
        "content",
        (
            "Lecture 5 | A-star graph search\n"
            + "Goal: trace graph search with an admissible but inconsistent heuristic.\n"
            + "Priority f(n) = g(n) + h(n). Reinsert a closed state if g improves.",
            "Directed edges: S to A: 3, S to B: 1, B to A: 1, A to G: 3, B to G: 8.\n"
            + "h(S) = 0, h(A) = 0, h(B) = 4, h(G) = 0.\n"
            + "Pop S, then A at 3, then B at 1. Reopen A at 2 via B.\n"
            + "Pop A at 2, then G at 5. The path is S-B-A-G.",
        ),
    ),
    (
        "lecture-5-resolution",
        "content",
        (
            "Lecture 5 | Resolution\nGoal: justify a resolvent from complementary literals.\n"
            + "Resolve P or Q with not P or R to obtain Q or R.\n"
            + "Exercise: Can the premise not Q establish R? Show each inference.",
            "Archive copy (slide caption): the edge from B to A costs 2.",
        ),
    ),
    (
        "lecture-6-consistency",
        "content",
        (
            "Lecture 6 | Consistency (reading; no recording in the archive)\n"
            + "Goal: test consistency on a directed edge.\n"
            + "A heuristic is consistent if h(u) <= c(u,v) + h(v) for each edge u to v.\n"
            + "Here h(B)=4, c(B,A)=1 and h(A)=0, so consistency fails.",
        ),
    ),
    (
        "lecture-7-uncertainty",
        "content",
        (
            "Lecture 7 | Introduction to uncertainty\n"
            + "1. Define a sample space.\n2. Recognize a probability event.\n"
            + "3. Compute a complement.\n4. Find a joint probability.\n"
            + "5. Marginalize a joint distribution.\n6. Compute a conditional probability.\n"
            + "7. Recognize independence.",
        ),
    ),
    (
        "sheet-6",
        "exercise",
        (
            "Sheet 6 | Search and logic\n"
            + "1(a) Use the Lecture 5 graph to show why B improves the cost of A.\n"
            + "1(b) Given P or Q, not P or R, and not Q, derive R in two resolutions.\n"
            + "2. Trace A-star until G is popped, listing popped nodes in order.\n"
            + "Generate neighbors in the listed order. Equal f uses the tutorial rule.\n"
            + "Edges: S to J (1), S to K (1), J to G (1), K to G (1). All h = 0.\n"
            + "Ignore equal-cost updates to a state already discovered.",
        ),
    ),
    (
        "sheet-6-solutions",
        "exercise",
        (
            "Sheet 6 | Released solutions\n"
            + "1(a) S-B costs 1 and B-A costs 1, so g(A) improves from 3 to 2.\n"
            + "1(b) First resolve on P to obtain Q or R. Then resolve on Q to obtain R.\n"
            + "2. Both paths have cost 2. The expansion trace depends on the tutorial rule.",
        ),
    ),
)

_RECORDING_ASSETS: Final = Path(__file__).resolve().parents[1] / "fixtures" / JOURNEY
_DURATION_S: Final = 399
_UNCERTAIN: Final = Interval(start_s=392, end_s=399)
_RESUME_AT: Final = 182
RECORDING_KEY: Final = "live-42026-5"
RECORDING_FILE: Final = Path(".tum-mcp/lectures") / RECORDING_KEY / "recording.mp4"


class Oracle(NamedTuple):
    """Independent answers for the assessor; never serialized into the seed."""

    graph_pops: tuple[tuple[str, int], ...]
    graph_path: tuple[str, ...]
    exercise_pops_latest: tuple[str, ...]
    exercise_pops_earliest: tuple[str, ...]
    exercise_path_latest: tuple[str, ...]
    correction: tuple[int, int]
    proof: tuple[tuple[int, int, str], ...]
    repeat: tuple[int, int]
    guest: tuple[int, int]
    unclear: tuple[int, int]
    resume_first_unread: tuple[int, int]
    practice: str
    routes: tuple[str, ...]


ORACLE: Final = Oracle(
    graph_pops=(("S", 0), ("A", 3), ("B", 1), ("A", 2), ("G", 5)),
    graph_path=("S", "B", "A", "G"),
    exercise_pops_latest=("S", "K", "J", "G"),
    exercise_pops_earliest=("S", "J", "K", "G"),
    exercise_path_latest=("S", "K", "G"),
    correction=(350, 357),
    proof=((364, 371, "Q or R"), (371, 378, "R")),
    repeat=(378, 392),
    guest=(252, 266),
    unclear=(392, 399),
    resume_first_unread=(182, 391),
    practice="Set h(B)=0. B pops before A, so it improves A while A is still open; no reopen.",
    routes=(
        "Study graph and changed-decision practice",
        "Lecture correction and two proof stages",
        "Exercise 1(a) prerequisite link and return to its owner",
        "Exercise remains usable when a prerequisite is documented missing",
        "Exercise 2 blocked before clarification and taught after it",
    ),
)


def _pdf(path: Path, pages: tuple[str, ...]) -> None:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject(k): NameObject(v)
            for k, v in (("/Type", "/Font"), ("/Subtype", "/Type1"), ("/BaseFont", "/Helvetica"))
        }
    )
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F"): font})}
        )
        lines = [
            line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in text.splitlines()
        ]
        stream = ContentStream(None, writer)
        stream.set_data(
            (
                "BT /F 13 Tf 17 TL 42 742 Td "
                + " T* ".join(f"({line}) Tj" for line in lines)
                + " ET"
            ).encode("ascii")
        )
        page.replace_contents(stream)
    _ = writer.write(path)


def _recording(root: Path) -> PreparedReceipt:
    media = root / RECORDING_FILE
    directory = media.parent
    _ = shutil.copytree(_RECORDING_ASSETS, directory, ignore=shutil.ignore_patterns("README.md"))
    transcript = (directory / "transcript.json").read_bytes()
    frames = (directory / "frames.json").read_bytes()
    duration = _DURATION_S
    recording = Recording(
        course_slug=JOURNEY,
        course_id=42026,
        recording_id=5,
        recorded_on=_MEETINGS[0],
        duration_s=duration,
    )
    validity = evaluate(
        RecordingTiming(duration_s=duration, silences=(SilenceMarker(start=391, end=392),))
    )
    receipt = PreparedReceipt(
        status="partial",
        key=recording.key,
        recording=recording,
        title="Search and resolution",
        checked_at=_AS_OF,
        validity=validity,
        source_revision=digest(media.read_bytes()),
        metadata_revision=digest(recording.model_dump_json().encode()),
        processed=validity.eligible,
        uncertain=(_UNCERTAIN,),
        transcript_sha256=digest(transcript),
        frames_sha256=digest(frames),
        bytes_downloaded=0,
        media_reused=0,
        chunks_reused=0,
        inference_s=0,
    )
    _ = (directory / "receipt.json").write_text(receipt.model_dump_json(), encoding="utf-8")
    return receipt


def seed(workspace: Path, scenario_id: str) -> None:
    """Populate a fresh author workspace with offline sources and a versioned resume checkpoint."""
    if scenario_id not in (JOURNEY, RESUME):
        raise LabError(f"No FAI fixture for {scenario_id!r}.")
    with tempfile.TemporaryDirectory(prefix="fai-fixture-") as temporary:
        staging = Path(temporary)
        resources: list[Resource] = []
        for key, kind, pages in _SOURCES:
            name = f"{key}.pdf"
            _pdf(staging / name, pages)
            resources.append(
                Resource(
                    key=key,
                    binding="local",
                    kind=kind,
                    title=key.replace("-", " "),
                    source_file=name,
                )
            )
        receipt = _recording(workspace)
        course = Course(
            key=JOURNEY,
            title="Fundamentals of Artificial Intelligence",
            semester="WS26/27",
            bindings=(
                Binding(key="local", provider="local", course_id=JOURNEY),
                Binding(key="live", provider="tum_live", course_id="42026", course_slug=JOURNEY),
            ),
        )
        resources.append(
            Resource(
                key=receipt.key,
                binding="live",
                kind="content",
                title=receipt.title,
                url=f"https://live.rbg.tum.de/w/{JOURNEY}/5",
                text=source_text(receipt),
            )
        )
        snapshot = Snapshot(
            schema_version=2,
            course=course,
            resources=tuple(resources),
            coverage=(
                Coverage(binding="local", status="complete", checked_at=_AS_OF),
                Coverage(binding="live", status="partial", checked_at=_AS_OF),
            ),
        )
        incoming = staging / "snapshot.json"
        _ = incoming.write_text(snapshot.model_dump_json(), encoding="utf-8")
        _ = sync(workspace, incoming, course_input=course.title)
    schedule = Schedule(
        sessions=tuple(
            Session(on=day, sources=keys, label=f"Lecture {index}", basis="course page")
            for index, (day, keys) in enumerate(
                zip(
                    _MEETINGS,
                    (
                        ("lecture-5-search", "lecture-5-resolution"),
                        ("lecture-6-consistency",),
                        ("lecture-7-uncertainty",),
                    ),
                    strict=True,
                ),
                start=5,
            )
        )
    )
    private = workspace / ".tum-mcp"
    _ = (private / "schedule.json").write_text(schedule.model_dump_json(), encoding="utf-8")
    if scenario_id == RESUME:
        materials = tuple(
            SourceVersion(key=item.resource.key, sha256=item.sha256)
            for item in load_state(workspace).resources
            if item.resource.key.startswith("lecture-5-") and item.sha256 is not None
        )
        saved = WorkingSelection(
            recording=receipt.key,
            transcript_sha256=receipt.transcript_sha256,
            materials=materials,
            decisions=(
                Decision(
                    interval=Interval(start_s=0, end_s=_RESUME_AT),
                    disposition="omit",
                    material="lecture-5-search",
                    pages="1-2",
                    reason="The deck already shows the graph, priorities and improved cost at A.",
                ),
            ),
        )
        path = private / "work/lecture-selection" / f"{receipt.key}.json"
        path.parent.mkdir(parents=True)
        _ = path.write_text(saved.model_dump_json(), encoding="utf-8")
        batch = Batch(
            course_key=JOURNEY,
            request="Prepare Lecture 5 from the recorded meeting.",
            items=(f"lecture/{receipt.key}",),
        )
        (private / "batches").mkdir()
        _ = (private / "batches/recorded-meeting.json").write_text(
            batch.model_dump_json(), encoding="utf-8"
        )
        task = Task(
            owner="codex:fixture-prior-session",
            batch="recorded-meeting",
            phase="paused",
            reason="The previous session ended with the recording selection in progress.",
        )
        _ = (private / "task.json").write_text(task.model_dump_json(), encoding="utf-8")


def release_clarification(workspace: Path) -> None:
    """Import the same erratum after the withheld checkpoint, regardless of author output."""
    state = load_state(workspace)
    snapshot = Snapshot(
        schema_version=2,
        course=state.course,
        retained_bindings=("live",),
        coverage=(Coverage(binding="local", status="partial", checked_at=_AS_OF),),
        resources=(
            Resource(
                key=CLARIFICATION_KEY,
                binding="local",
                kind="exercise",
                title="Sheet 6 tutorial erratum",
                text=_RULE + "\n",
            ),
        ),
    )
    with tempfile.TemporaryDirectory(prefix="fai-erratum-") as temporary:
        incoming = Path(temporary) / "snapshot.json"
        _ = incoming.write_text(snapshot.model_dump_json(), encoding="utf-8")
        _ = sync(workspace, incoming)
