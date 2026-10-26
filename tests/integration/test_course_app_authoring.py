import json
from pathlib import Path

from tum_mcp.study_build import build, read_content
from tum_mcp.study_store import load_state


def test_either_preparation_order_and_targeted_update_preserve_other_workspace(
    exercise_project: Path,
) -> None:
    root = exercise_project
    study = root / "study/content.json"
    exercises = root / "study/exercises.json"
    original_study = study.read_bytes()
    original_exercises = exercises.read_bytes()
    # Exercises can be prepared first, without inventing a Study prerequisite unit.
    study.unlink()
    report = build(root, publish=False)
    assert report.units == 0 and report.exercises == 2
    study.write_bytes(original_study)
    build(root, publish=False)
    # Study can also be prepared first; the second workspace changes only the payload.
    exercises.unlink()
    build(root, publish=False)
    exercises.write_bytes(original_exercises)
    build(root, publish=False)
    assets = {
        path.name: path.read_bytes()
        for path in (root / "study").iterdir()
        if path.is_file() and path.suffix in {".mjs", ".css", ".html"} and path.name != "data.mjs"
    }
    payload = json.loads(original_exercises)
    untouched = payload["sets"][0]["exercises"][1]
    payload["sets"][0]["exercises"][0]["steps"][0]["hints"].append("Compare complete path costs.")
    exercises.write_text(json.dumps(payload))
    build(root, publish=False)
    assert study.read_bytes() == original_study
    assert json.loads(exercises.read_bytes())["sets"][0]["exercises"][1] == untouched
    assert all((root / "study" / name).read_bytes() == value for name, value in assets.items())
    assert read_content(root).course_key == load_state(root).course.key


def test_second_course_uses_the_same_template_without_demo_identity_assumptions(
    tmp_path: Path,
) -> None:
    from tum_mcp.study_sync import sync

    fixture = Path(__file__).parents[1] / "fixtures/course_app"
    snapshot = json.loads((fixture / "snapshot.json").read_bytes())
    snapshot["course"].update(key="probability-pilot", title="Conditional probability")
    snapshot["course"]["bindings"][0]["course_id"] = "probability-pilot"
    snapshot["resources"] = [r for r in snapshot["resources"] if r["key"] == "probability"]
    incoming = tmp_path / "incoming.json"
    incoming.write_text(json.dumps(snapshot))
    root = tmp_path / "probability"
    sync(root, incoming, course_input="Conditional probability")
    (root / "app").mkdir()
    payload = (fixture / "probability-exercises.json").read_bytes()
    (root / "app/exercises.json").write_bytes(payload)
    report = build(root, publish=False)
    assert report.units == 0 and report.exercises == 1
    # Adding Study later retains the original exercises and shared assets.
    content = json.loads((fixture / "content.json").read_bytes())
    content["course_key"] = "probability-pilot"
    content["units"] = [u for u in content["units"] if u["key"] == "probability"]
    (root / "app/content.json").write_text(json.dumps(content))
    assert build(root, publish=False).units == 1
    assert (root / "app/exercises.json").read_bytes() == payload
