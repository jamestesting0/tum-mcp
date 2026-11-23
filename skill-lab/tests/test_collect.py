import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from skill_lab import scenarios, shim, variants
from skill_lab.collect import checker_phases, collect_run, review_stats, transcript_stats

from tum_mcp.course.app.browser_evidence import browser_choice, browser_identity, save_receipt
from tum_mcp.course.app.build import current_data
from tum_mcp.course.checks.batch import Batch, assess_batch
from tum_mcp.course.content.exam_data import read_exam
from tum_mcp.course.content.store import document_writes, read_document
from tum_mcp.course.project.store import apply
from tum_mcp.course.workflow.tasks import begin


def _write(path, events):
    path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")


def _calibration_run(
    lab_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    project: str | None = ".",
    skills: tuple[str, ...] | list[str] = (),
    expected: dict[str, list[str]] | None = None,
    scenario: str | None = None,
) -> Path:
    directory = lab_state / "rounds/r1/runs/candidate-1"
    workspace = directory / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(variants, "python_of", lambda _: Path(sys.executable))
    (directory / "run.json").write_text(
        json.dumps(
            {
                "author": "codex:gpt-6.1-terra:high",
                "status": "completed",
                "variant": "candidate",
                "project": project,
                "scenario": scenario,
                "turns": [
                    {"turn": 1, "parts": [], "skills": skills, "expected_items": expected or {}}
                ],
            }
        )
    )
    return directory


def _study_cli(project: Path, *arguments: str) -> str:
    return subprocess.run(
        [sys.executable, "-I", "-m", "tum_mcp", "study", *arguments, str(project)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_demo_collection_matches_independently_read_full_report(
    lab_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    turn = scenarios.load("demo-calibration").turns[0]
    directory = _calibration_run(
        lab_state, monkeypatch, skills=turn.skills, expected=turn.expected_items
    )
    project = directory / "workspace"
    _study_cli(project, "demo")
    expected = json.loads(_study_cli(project, "report", "--json"))

    measured = collect_run("r1", "candidate-1", visuals=False)

    assert measured["quality_flags"] == len(expected["quality"]) == 20
    assert measured["review_passed"] is expected["review"]["gate"]
    assert measured["render_passed"] is expected["render"]["passed"]
    assert measured["delivery"]["study"]["readable_items"] == ["study/components"]
    assert measured["delivery"]["study"]["missing_items"] == []
    assert measured["coverage_gaps"] == sum(
        len(expected["coverage"][field])
        for field in (
            "not_inspected",
            "outcome_gaps",
            "enrichment_gaps",
            "sources_without_outcomes",
            "unprepared_items",
            "units_without_outcomes",
        )
    ) + sum(
        len(expected["coverage"]["cheatsheet"][field])
        for field in ("gaps", "sources_without_requirements", "entries_without_requirement")
    )
    assert json.loads((directory / "report.json").read_text()) == expected


@pytest.mark.parametrize(
    ("project", "body", "exit_code", "status", "count"),
    [
        (None, "", 0, "not_measured", None),
        (".", "", 0, "failed", None),
        (".", "{", 0, "failed", None),
        (".", "{}", 0, "failed", None),
        (".", "specific report failure", 3, "failed", None),
        (".", None, 0, "measured", 0),
    ],
)
def test_report_status_distinguishes_unavailable_and_clean(
    lab_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    project: str | None,
    body: str | None,
    exit_code: int,
    status: str,
    count: int | None,
) -> None:
    directory = _calibration_run(lab_state, monkeypatch, project=project)
    if body is None:
        # A real empty course report can be measured without producing a workspace.
        root = directory / "workspace"
        _study_cli(root, "demo")
        for name in ("study", "exercises", "exam"):
            shutil.rmtree(root / "app" / name)
        assert json.loads(_study_cli(root, "report", "--json"))["quality"] == []
    else:
        emitter = tmp_path / "report-python"
        emitter.write_text(
            f"#!{sys.executable}\nimport sys\n"
            f"print({body!r}, file=sys.stderr if {exit_code} else sys.stdout)\n"
            f"sys.exit({exit_code})\n"
        )
        emitter.chmod(0o755)
        monkeypatch.setattr(variants, "python_of", lambda _: emitter)

    metrics = collect_run("r1", "candidate-1", visuals=False)

    assert (metrics.get("report_status"), metrics.get("quality_flags")) == (status, count)
    assert bool(metrics["report_error"]) is (status == "failed")
    if exit_code:
        assert "specific report failure" in metrics["report_error"]


@pytest.mark.parametrize(
    ("skills", "retained", "expected", "outcomes"),
    [
        (["prepare-exams"], {"exam"}, {}, {"exam": "partial"}),
        (
            ["prepare-lecture"],
            {"lectures"},
            {"lectures": ["lecture/missing"]},
            {"lectures": "partial"},
        ),
        (
            ["prepare-study", "prepare-exercises"],
            {"exercises"},
            {},
            {"study": "absent", "exercises": "partial"},
        ),
    ],
)
def test_delivery_is_scoped_to_the_request(
    lab_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    skills: list[str],
    retained: set[str],
    expected: dict[str, list[str]],
    outcomes: dict[str, str],
) -> None:
    directory = _calibration_run(lab_state, monkeypatch, skills=skills, expected=expected)
    project = directory / "workspace"
    _study_cli(project, "demo", *(["--lectures"] if "lectures" in retained else []))
    for name in {"study", "exercises", "exam", "lectures"} - retained:
        folder = project / "app" / name
        if folder.is_dir():
            shutil.rmtree(folder)

    metrics = collect_run("r1", "candidate-1", visuals=False)

    assert {name: row["status"] for name, row in metrics.get("delivery", {}).items()} == outcomes
    if expected:
        assert metrics["delivery"]["lectures"]["missing_items"] == ["lecture/missing"]


@pytest.mark.parametrize(
    ("case", "status", "problem"),
    [
        ("draft", "complete", None),
        ("different-controller", "complete", None),
        ("changed-capture", "partial", "browser evidence is missing"),
        ("stale-build", "partial", "Build the complete current draft."),
        ("unrequested-sibling", "complete", None),
        ("formal-review", "partial", "no current verdict"),
    ],
)
def test_exam_delivery_uses_applicable_readiness(
    lab_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    status: str,
    problem: str | None,
) -> None:
    item = "exam/mock/demo-forecast/demo-f1"
    directory = _calibration_run(
        lab_state, monkeypatch, skills=["prepare-exams"], expected={"exam": [item]}
    )
    project = directory / "workspace"
    _study_cli(project, "demo")
    for workspace in ("study", "exercises"):
        shutil.rmtree(project / "app" / workspace)
    (project / "app/data.mjs").write_bytes(current_data(project))
    exam = read_exam(project)
    assert exam is not None
    monkeypatch.setenv("TUM_MCP_BROWSER", sys.executable)
    identity = browser_identity(project, browser_choice())
    picture = ".tum-mcp/visuals/exam.png"
    (project / picture).parent.mkdir(exist_ok=True)
    Image.new("RGB", (8, 8)).save(project / picture)
    save_receipt(
        project,
        identity,
        {
            "interact/desktop/#exam/mock/demo-forecast": True,
            "shell/desktop/light/exam": True,
            "shell/desktop/dark/exam": True,
            "visual/desktop/exam": True,
        },
        captures={"visual/desktop/exam": (picture,)},
    )
    items = (item, "exam/mock/unrequested/missing") if case == "unrequested-sibling" else (item,)
    batch = Batch(course_key=exam.course_key, request="Prepare one mock question.", items=items)
    batch_path = project / ".tum-mcp/batches/mock.json"
    batch_path.parent.mkdir()
    batch_path.write_text(batch.model_dump_json())
    begin(project, "mock", review_rounds=int(case == "formal-review"), owner="test")
    if case == "stale-build":
        (project / "app/data.mjs").unlink()
    if case == "changed-capture":
        Image.new("RGB", (12, 12)).save(project / picture)
    readiness = assess_batch(project, "mock")
    assert readiness.ready is (case in {"draft", "different-controller", "formal-review"}), (
        readiness.problems
    )
    if case == "different-controller":
        monkeypatch.setattr(
            "tum_mcp.course.checks.preparation.browser_identity",
            lambda *_: identity.model_copy(update={"browser": "0" * 64}),
        )

    measured = collect_run("r1", "candidate-1", visuals=False)

    row = measured["delivery"]["exam"]
    assert item in row["readable_items"]
    assert row["missing_items"] == []
    assert row["status"] == status, row["problems"]
    if problem is not None:
        assert any(problem in issue for issue in row["problems"]), row["problems"]
    else:
        assert row["problems"] == []
    assert measured["review_passed"] is False


def test_chapter_only_lecture_is_a_readable_delivery(lab_state, monkeypatch):
    key = "lecture/bfs-lecture"
    directory = _calibration_run(
        lab_state, monkeypatch, skills=["prepare-lecture"], expected={"lectures": [key]}
    )
    project = directory / "workspace"
    _study_cli(project, "demo", "--lectures")
    data = read_document(project, "lectures")
    lecture = data["lectures"][0]
    assert lecture["chapters"]
    lecture.update(notes=[], highlights=[])
    data["evidence"] = []
    apply(project, document_writes(project, "lectures", data))
    row = collect_run("r1", "candidate-1", visuals=False)["delivery"]["lectures"]
    assert row["readable_items"] == [key]
    assert row["missing_items"] == []


def test_unavailable_variant_keeps_delivery_unmeasured(lab_state, monkeypatch, tmp_path):
    _calibration_run(lab_state, monkeypatch, skills=["prepare-lecture"])
    monkeypatch.setattr(variants, "python_of", lambda _: tmp_path / "removed-variant")
    metrics = collect_run("r1", "candidate-1", visuals=False)
    assert metrics["delivery"]["lectures"]["status"] == "unmeasured"
    assert metrics["delivery"]["lectures"]["problems"]
    assert metrics["report_status"] == "failed"


def test_codex_usage_is_counted_once_per_thread(tmp_path):
    transcript = tmp_path / "transcript"
    transcript.mkdir()
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "turns": [
                    {"turn": 1, "parts": [{"label": "turn-1"}, {"label": "turn-1-reply-1"}]},
                    {"turn": 2, "parts": [{"label": "turn-2"}]},
                ]
            }
        )
    )
    command = {
        "type": "item.completed",
        "item": {"type": "command_execution", "aggregated_output": "abc\u03c0", "exit_code": 0},
    }
    _write(
        transcript / "turn-1.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            command,
            {"type": "turn.completed", "usage": {"input_tokens": 53027776}},
        ],
    )
    _write(
        transcript / "turn-1-reply-1.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            {"type": "turn.completed", "usage": {"input_tokens": 53366734}},
        ],
    )
    _write(
        transcript / "turn-2.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            command,
            {"type": "turn.completed", "usage": {"input_tokens": 114658765}},
        ],
    )

    stats = transcript_stats(tmp_path, "codex")

    assert stats["tokens"] == 114658765
    assert stats["turn_tokens"] == [53027776, 338958, 61292031]
    assert stats["output_chars"] == 8
    assert stats["output_bytes"] == 10
    assert stats["tool_calls"] == 2
    assert all("start" not in phase and "minutes" not in phase for phase in stats["phase_table"])


def test_review_stats_counts_checker_sessions_and_verdicts(tmp_path):
    broker = tmp_path / ".lab-broker"
    broker.mkdir()
    for name, stdout in (
        ("a", {"recorded": ["study/x"], "verdicts": {}}),
        ("b", {"recorded": ["study/x"], "opened": 2, "resolved": 0}),
        ("c", {"summary": {"passed": True}}),
    ):
        (broker / f"{name}.response.json").write_text(
            json.dumps({"code": "0", "stdout": json.dumps(stdout)}), encoding="utf-8"
        )
    packets = tmp_path / "course" / ".tum-mcp" / "review" / "packets"
    packets.mkdir(parents=True)
    (packets / "r1-study-unit-1.answer.json").write_text(
        json.dumps(
            {"items": [{"checks": {"a": {"verdict": "pass"}, "b": {"verdict": "uncertain"}}}]}
        ),
        encoding="utf-8",
    )

    stats = review_stats(tmp_path)

    assert stats == {
        "plan_checks": 1,
        "packet_checks": 1,
        "verdicts": {"pass": 1, "uncertain": 1},
    }


def test_uncertain_verdicts_are_grouped_by_missing_evidence(tmp_path):
    packets = tmp_path / "course" / ".tum-mcp" / "review" / "packets"
    packets.mkdir(parents=True)
    checks = {
        "a": {"verdict": "uncertain", "missing": "Slide 4 image cannot be opened."},
        "b": {"verdict": "uncertain", "missing": "Slide 4 image cannot be opened."},
        "c": {"verdict": "uncertain", "reason": "Legacy source is unavailable."},
        "d": {"verdict": "uncertain"},
        "e": {"verdict": "pass", "reason": "Read the slide."},
    }
    (packets / "r1.answer.json").write_text(json.dumps({"items": [{"checks": checks}]}))

    stats = review_stats(tmp_path)

    assert stats["uncertain_causes"] == {
        "Slide 4 image cannot be opened.": 2,
        "Legacy source is unavailable.": 1,
    }
    assert stats["verdicts"] == {"uncertain": 4, "pass": 1}


def test_collected_phase_table_orders_commands_by_start_in_each_turn(lab_state):
    tmp_path = lab_state / "rounds" / "r1" / "runs" / "candidate-1"
    transcript = tmp_path / "transcript"
    transcript.mkdir(parents=True)
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "author": "codex:gpt-6.1-terra:high:fast",
                "status": "completed",
                "variant": "candidate",
                "turns": [
                    {"turn": 2, "parts": [{"label": "turn-2"}]},
                    {"turn": 1, "parts": [{"label": "turn-1"}]},
                ],
            }
        )
    )
    first = {
        "id": "p",
        "type": "command_execution",
        "command": "tum-mcp review run-checker . --plans",
    }
    second = {"id": "b", "type": "command_execution", "command": "tum-mcp study build ."}
    _write(
        transcript / "turn-1.jsonl",
        [
            {"type": "item.started", "timestamp": "2026-11-14T00:00:00Z", "item": first},
            {"type": "item.started", "timestamp": "2026-11-14T00:01:00Z", "item": second},
            {"type": "item.completed", "timestamp": "2026-11-14T00:02:00Z", "item": second},
            {"type": "item.completed", "timestamp": "2026-11-14T00:03:00Z", "item": first},
        ],
    )
    _write(
        transcript / "turn-2.jsonl",
        [
            {
                "type": "item.started",
                "_lab_timestamp": "2026-11-14T00:04:00Z",
                "item": {
                    "id": "r",
                    "type": "command_execution",
                    "command": "tum-mcp study rebuild .",
                },
            },
            {
                "type": "item.completed",
                "_lab_timestamp": "2026-11-14T00:05:30Z",
                "item": {
                    "id": "r",
                    "type": "command_execution",
                    "command": "tum-mcp study rebuild .",
                },
            },
        ],
    )

    metrics = collect_run("r1", "candidate-1", visuals=False)
    phases = metrics["phase_table"]

    assert json.loads((tmp_path / "metrics.json").read_text())["phase_table"] == phases
    assert [(p["turn"], p["kind"], p["start"], p["end"], p["minutes"]) for p in phases] == [
        (1, "plan_check", "2026-11-14T00:00:00Z", "2026-11-14T00:03:00Z", 3),
        (1, "study.build", "2026-11-14T00:01:00Z", "2026-11-14T00:02:00Z", 1),
        (2, "study.rebuild", "2026-11-14T00:04:00Z", "2026-11-14T00:05:30Z", 1.5),
    ]


def test_checker_phases_include_refused_answers_and_repairs(tmp_path):
    broker = tmp_path / ".lab-broker"
    broker.mkdir()
    _write(
        broker / "packet.sessions.jsonl",
        [
            {
                "event": "started",
                "kind": "review_packet",
                "attempt": 0,
                "timestamp": "2026-11-14T00:00:10Z",
            },
            {
                "event": "completed",
                "attempt": 0,
                "status": "completed",
                "timestamp": "2026-11-14T00:01:10Z",
            },
            {
                "event": "started",
                "kind": "review_packet",
                "attempt": 1,
                "timestamp": "2026-11-14T00:01:20Z",
            },
            {
                "event": "completed",
                "attempt": 1,
                "status": "failed",
                "timestamp": "2026-11-14T00:01:50Z",
            },
        ],
    )
    parent = {
        "turn": 2,
        "part": "turn-2",
        "kind": "review_packet",
        "start": "2026-11-14T00:00:00Z",
        "end": "2026-11-14T00:02:00Z",
    }

    phases = checker_phases(tmp_path, [parent])

    assert [(p["turn"], p["attempt"], p["repair"], p["status"], p["minutes"]) for p in phases] == [
        (2, 0, False, "refused", 1),
        (2, 1, True, "failed", 0.5),
    ]
    assert checker_phases(tmp_path / "old-run", []) == []


def test_checker_observation_keeps_output_and_records_every_invocation(tmp_path):
    broker = tmp_path / ".lab-broker"
    broker.mkdir()
    log = broker / "packet.sessions.jsonl"
    command = [
        sys.executable,
        "-I",
        str(Path(shim.__file__)),
        "--lab-checker",
        str(log),
        "review_packet",
        sys.executable,
        "-c",
        "import sys; print('private checker prompt \u03c0'); sys.exit(3)",
    ]

    results = [
        subprocess.run(
            [*command[:-1], command[-1].replace("exit(3)", f"exit({code})")],
            capture_output=True,
            text=True,
            check=False,
        )
        for code in (0, 3)
    ]

    assert [(result.returncode, result.stdout) for result in results] == [
        (0, "private checker prompt \u03c0\n"),
        (3, "private checker prompt \u03c0\n"),
    ]
    phases = checker_phases(tmp_path, [])
    assert [(p["attempt"], p["repair"], p["status"]) for p in phases] == [
        (0, False, "refused"),
        (1, True, "failed"),
    ]
    assert all(phase["minutes"] >= 0 for phase in phases)
    assert "private checker prompt" not in log.read_text()
