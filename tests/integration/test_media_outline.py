import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.media import audio_project, outline
from tum_mcp.course.media import video_project as project
from tum_mcp.course.media.video_sources import read_sources


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "demo"
    assert CliRunner().invoke(app, ["study", "demo", str(root)]).exit_code == 0
    return root


def test_every_outline_covers_its_source_and_only_waits_for_writing(
    demo: Path, tmp_path: Path
) -> None:
    # Authors reverse-engineered locator hashes and dropped parts; an outline starts complete.
    sources = read_sources(demo)
    unit = next(key for key in sources.items if key.startswith("study/"))
    exercise = next(key for key in sources.items if key.startswith("exercises/"))
    pattern = next(key for key in sources.items if key.startswith("exam/patterns/"))
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "units": [{"unit": unit.split("/")[1], "decision": "video", "reason": "Process."}],
                "exercises": [
                    {
                        "exercise": dict(
                            zip(("set", "exercise"), exercise.split("/")[1:], strict=True)
                        ),
                        "decision": "video",
                        "reason": "Worked.",
                    }
                ],
                "patterns": [
                    {"pattern": pattern.split("/")[2], "decision": "video", "reason": "Method."}
                ],
            }
        ),
        encoding="utf-8",
    )
    planned = project.plan(demo, selection)
    assert len(planned.videos) == 3
    for entry in planned.videos:
        assert entry.stem
        written = outline.video(demo, entry.stem)
        report = project.check(demo, entry.stem)
        assert report.errors and written["to_write"] == len(report.errors)
        assert all(error.startswith("outline.unwritten") for error in report.errors), report.errors
        with pytest.raises(Exception, match="only a new draft"):
            outline.video(demo, entry.stem)

    group, key = exercise.split("/")[1:]
    written = outline.audio(
        demo, "01_practice", [f"exercise:{group}/{key}", f"pattern:{pattern.split('/')[2]}"]
    )
    errors = audio_project.check(demo, "01_practice")["errors"]
    assert errors and len(errors) == written["to_write"]
    assert all(error.startswith("outline.unwritten") for error in errors), errors
