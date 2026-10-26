import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course_app_paths import app_folder
from tum_mcp.errors import CampusError
from tum_mcp.lecture_data import read_lectures
from tum_mcp.study_build import build
from tum_mcp.study_status import project_status
from tum_mcp.study_store import load_state

FIXTURES = Path(__file__).parents[1] / "fixtures/course_app"


@pytest.fixture
def lecture_project(exercise_project: Path) -> Path:
    state = load_state(exercise_project)
    source = next(item for item in state.resources if item.resource.key == "graphs")
    payload = json.loads((FIXTURES / "lectures.json").read_bytes())
    payload["course_key"] = state.course.key
    payload["lectures"][0]["sources"][0]["sha256"] = source.sha256
    for item in payload["evidence"]:
        item["source_sha256"] = source.sha256
    (exercise_project / "study/lectures.json").write_text(json.dumps(payload))
    private = exercise_project / ".tum-mcp/lecture-assets"
    shutil.copytree(FIXTURES / "lecture-assets", private)
    return exercise_project


def payload(root: Path) -> dict:
    return json.loads(
        (root / app_folder(root) / "data.mjs")
        .read_text()
        .removeprefix("export default ")
        .removesuffix(";\n")
    )


def bytes_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "selected",
    [
        ("study",),
        ("exercises",),
        ("lectures",),
        ("study", "exercises"),
        ("study", "lectures"),
        ("exercises", "lectures"),
        ("study", "exercises", "lectures"),
    ],
)
@pytest.mark.parametrize("folder", ["app", "study"])
def test_all_seven_workspace_subsets_build_without_forced_assessments(
    lecture_project: Path, selected: tuple[str, ...], folder: str
) -> None:
    root = lecture_project
    if folder == "app":
        (root / "study").rename(root / "app")
    for workspace, filename in (
        ("study", "content.json"),
        ("exercises", "exercises.json"),
        ("lectures", "lectures.json"),
    ):
        if workspace not in selected:
            (root / folder / filename).unlink()
    report = build(root, publish=False)
    data = payload(root)
    assert data["workspaces"] == list(selected)
    assert report.lectures == (1 if "lectures" in selected else 0)
    if "lectures" in selected:
        notes = data["lectures"]["lectures"][0]
        assert notes["sections"][0]["citations"][0]["url"].endswith("?t=20")
        assert notes["sections"][0]["figures"][0]["url"].endswith("?t=37")
        assert notes["revision"] == read_lectures(root).lectures[0].semantic_revision
    before = bytes_tree(root)
    build(root, publish=False)
    assert bytes_tree(root) == before


def test_notes_schema_inspect_and_status_report_authored_lectures(lecture_project: Path) -> None:
    build(lecture_project, publish=False)
    runner = CliRunner()
    schema = runner.invoke(app, ["study", "schema", "lectures"])
    inspected = runner.invoke(app, ["study", "inspect", str(lecture_project)])
    assert schema.exit_code == inspected.exit_code == 0
    assert "LectureSection" in json.loads(schema.output)["$defs"]
    assert json.loads(inspected.output)["lectures"] == 1
    assert project_status(lecture_project).lecture_notes == "authored"


@pytest.mark.parametrize(
    "failure",
    [
        "changed_source",
        "other_course",
        "hash",
        "dimensions",
        "conflicting_dimensions",
        "unsafe_path",
        "symbolic",
        "custom_template",
    ],
)
def test_invalid_lecture_inputs_preserve_the_previous_app_and_authored_bytes(
    lecture_project: Path, failure: str
) -> None:
    root = lecture_project
    build(root, publish=False)
    notes_path = root / "study/lectures.json"
    notes = json.loads(notes_path.read_text())
    figure = notes["lectures"][0]["sections"][0]["figures"][0]
    asset = root / ".tum-mcp" / figure["asset"]
    if failure == "changed_source":
        source = next(item for item in load_state(root).resources if item.resource.key == "graphs")
        (root / source.path).write_text("Edited source")
    elif failure == "other_course":
        notes["course_key"] = "another-course"
    elif failure == "hash":
        asset.write_bytes(asset.read_bytes() + b"changed")
    elif failure == "dimensions":
        figure["width"] -= 1
    elif failure == "conflicting_dimensions":
        wrong = dict(figure, width=figure["width"] - 1)
        notes["lectures"][0]["sections"][0]["figures"].insert(0, wrong)
    elif failure == "unsafe_path":
        figure["asset"] = "../personal.png"
    elif failure == "symbolic":
        original = root / "original.png"
        asset.rename(original)
        asset.symlink_to(original)
    else:
        (root / "study/styles.css").write_text("customized")
    notes_path.write_text(json.dumps(notes))
    before = bytes_tree(root)
    with pytest.raises(CampusError):
        build(root, publish=False)
    assert bytes_tree(root) == before


def test_removing_a_figure_deletes_only_its_managed_copy(lecture_project: Path) -> None:
    root = lecture_project
    build(root, publish=False)
    path = root / "study/lectures.json"
    notes = json.loads(path.read_text())
    asset = root / "study" / notes["lectures"][0]["sections"][0]["figures"][0]["asset"]
    custom = root / "study/lecture-assets/my-diagram.png"
    custom.write_bytes(b"user image")
    notes["lectures"][0]["sections"][0]["figures"] = []
    path.write_text(json.dumps(notes))
    build(root, publish=False)
    assert not asset.exists() and custom.read_bytes() == b"user image"


def test_failure_after_managed_figure_deletion_restores_the_previous_app(
    lecture_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import study_store

    root = lecture_project
    build(root, publish=False)
    path = root / "study/lectures.json"
    notes = json.loads(path.read_text())
    notes["lectures"][0]["sections"][0]["figures"] = []
    path.write_text(json.dumps(notes))
    before = bytes_tree(root)
    original = study_store.private_write

    def fail_manifest(destination: Path, content: bytes) -> None:
        if destination.name == ".lecture-assets.json":
            raise PermissionError("Synthetic final asset transaction failure")
        original(destination, content)

    monkeypatch.setattr(study_store, "private_write", fail_manifest)
    with pytest.raises(CampusError, match="restored"):
        build(root, publish=False)
    assert bytes_tree(root) == before
