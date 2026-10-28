import json
from pathlib import Path

from material_fixture import material_project, pdf_bytes
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.study_duplicates import near_candidates
from tum_mcp.study_store import load_state

TASK = (
    "Task 1 Apply the observer pattern to the weather station so that every display is "
    "notified when a measurement changes and explain why the subject must not depend on "
    "concrete display classes in your design"
)
OTHER = (
    "Task 1 Model a library system with a class diagram that shows borrowing rules, the "
    "multiplicity between members and loans, and an association class for reservations"
)


def test_exact_copies_near_copies_and_scans_are_reported_separately(tmp_path: Path) -> None:
    paper = pdf_bytes([TASK, "Task 2 Strategy pattern for sorting"])
    root = material_project(
        tmp_path,
        {
            "exam-2023": ("exam", paper),
            "exam-2023-copy": ("exam", paper),
            "exam-2023-annotated": ("exam", pdf_bytes([TASK + " student note", "Task 2 Strategy"])),
            "exam-2022": ("exam", pdf_bytes([OTHER])),
            "exam-2021-scan": ("exam", pdf_bytes(["", ""])),
            "lecture": ("content", pdf_bytes([TASK])),
        },
    )
    report = near_candidates(root, load_state(root))
    assert [group.keys for group in report.exact] == [("exam-2023", "exam-2023-copy")]
    assert report.exact[0].preferred == "exam-2023"
    pairs = {(pair.left, pair.right) for pair in report.near}
    assert pairs == {("exam-2023", "exam-2023-annotated")}
    assert report.needs_visual == ("exam-2021-scan",)


def test_inspect_lists_exact_groups_without_reading_text(tmp_path: Path) -> None:
    root = material_project(
        tmp_path, {"a": ("content", b"# Same deck"), "b": ("content", b"# Same deck")}
    )
    result = CliRunner().invoke(app, ["study", "inspect", str(root)])
    assert result.exit_code == 0, result.output
    groups = json.loads(result.output)["duplicate_sources"]
    assert groups == [{"sha256": groups[0]["sha256"], "keys": ["a", "b"], "preferred": "a"}]
    assert not (root / ".tum-mcp/cache/text").exists()
