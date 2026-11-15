import json
from pathlib import Path

import pytest
from documents import content_file

from tum_mcp.course.app.build import build
from tum_mcp.errors import CampusError, Code


def _data(project: Path) -> dict:
    return json.loads(
        (project / "app/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )


def test_combined_build_includes_prepared_guidance_and_revisions(exercise_project: Path) -> None:
    # Given both authored workspaces bound to reviewed local source bytes.
    before = _data(exercise_project)
    # When the existing builder prepares the combined course.
    build(exercise_project, publish=False)
    data = _data(exercise_project)
    # Then guidance is available without changing Study identities or data.
    assert data["workspaces"] == ["study", "exercises"]
    assert data["units"] == before["units"]
    exercise = data["exercises"]["sets"][0]["exercises"][0]
    assert exercise["steps"][0]["check"]["answer"] == 3
    assert len(exercise["revision"]) == 64


def test_exercises_only_build_requires_no_dummy_study_content(exercise_project: Path) -> None:
    # Given an exercises-only course with the same source inventory.
    (content_file(exercise_project, "study")).unlink()
    # When building prepared content.
    build(exercise_project, publish=False)
    # Then the sole available workspace is Exercises, with no authored Study stub.
    assert _data(exercise_project)["workspaces"] == ["exercises"]
    assert _data(exercise_project)["units"] == []
    assert not (content_file(exercise_project, "study")).exists()


def test_exercises_alone_are_reviewable_and_study_added_later_asks_for_links(
    exercise_project: Path,
) -> None:
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.checks.links import undecided
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.review.loop import load

    # Given an exercises-only course.
    study = content_file(exercise_project, "study")
    saved = study.read_bytes()
    study.unlink()
    exercises = read_exercises(exercise_project)
    # Then review loads its items and flags, and no link to a missing workspace is asked for.
    context = load(exercise_project)
    assert {key.split("/")[0] for key in context.items} == {"exercises", "course"}
    assert not undecided(exercise_project, None, exercises, None, None)
    # When Study is added later, the exercise without a link to it is asked about.
    study.write_bytes(saved)
    pairs = undecided(exercise_project, read_content(exercise_project), exercises, None, None)
    assert [pair.item for pair in pairs] == ["exercises/sheet-1/sample-minimum-proof"]


def test_an_exercise_part_map_needs_no_gate_and_its_needs_link_study(
    exercise_project: Path,
) -> None:
    from tum_mcp.course.app.build import read_content as read_document_model
    from tum_mcp.course.checks.plans import Plan, gated, need_problems, plan_packet, plan_path
    from tum_mcp.course.content.store import read_document
    from tum_mcp.errors import CampusError

    item = "exercises/sheet-1/sample-minimum-proof"
    study = read_document(exercise_project, "study")
    assert study is not None
    unit, block = next((u, b["key"]) for u in study["units"] for b in u["blocks"] if b.get("key"))
    need = {"idea": "the minimum", "unit": unit["key"], "block": block}

    def plan(*needs: dict) -> Plan:
        part = {"part": "a", "answer": "3", "method": "Compare.", "needs": list(needs)}
        return Plan.model_validate({"item": item, "parts": [part]})

    # An exercise's part map is checked by code; Study plans still go to a checker.
    assert not gated(item) and gated(f"study/{unit['key']}")
    path = plan_path(exercise_project, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan(need).model_dump_json())
    with pytest.raises(CampusError, match="needs no plan check"):
        plan_packet(exercise_project, (item,))
    assert all(p["item"] != item for p in plan_packet(exercise_project)["plans"])
    # A need links the block that teaches it, and the exercise lists the same link.
    linked = {"prerequisites": [{"unit": unit["key"], "block": block, "explanation": "x"}]}
    assert need_problems(exercise_project, plan(need), linked) == []
    assert "prerequisites" in need_problems(exercise_project, plan(need), {"prerequisites": []})[0]
    wrong = need_problems(exercise_project, plan(need | {"block": "nowhere"}), None)
    assert "has no block nowhere" in wrong[0]
    # An unlinked need gives its reason; without one it is reported.
    assert need_problems(exercise_project, plan({"idea": "sets"}), None)
    assert not need_problems(exercise_project, plan({"idea": "sets", "reason": "Given."}), None)
    # `study links` lists the need that still lacks a link, with candidate passages.
    from tum_mcp.course.checks.links import open_needs

    path.write_text(plan({"idea": "the minimum"}).model_dump_json())
    [listed] = open_needs(exercise_project, read_document_model(exercise_project))
    assert (listed["item"], listed["need"]) == (item, "the minimum")
    # Without Study, needs stay inline reminders.
    content_file(exercise_project, "study").unlink()
    assert need_problems(exercise_project, plan({"idea": "sets"}), {"prerequisites": []}) == []


@pytest.mark.parametrize("fault", ["course", "source"])
def test_invalid_exercise_binding_preserves_the_last_verified_build(
    exercise_project: Path, fault: str
) -> None:
    # Given an edited exercise file that cannot be trusted for this inventory.
    path = content_file(exercise_project, "exercises")
    payload = json.loads(path.read_bytes())
    if fault == "course":
        payload["course_key"] = "another-course"
    else:
        for exercise in payload["sets"][0]["exercises"]:
            exercise["sources"][0]["sha256"] = "b" * 64
    path.write_text(json.dumps(payload))
    before = (exercise_project / "app/data.mjs").read_bytes()
    # When rebuilding, neither a foreign exercise nor stale content can disappear silently.
    with pytest.raises(CampusError) as caught:
        build(exercise_project, publish=False)
    assert caught.value.code == (Code.SCOPE_DENIED if fault == "course" else Code.STALE_RESULT)
    assert (exercise_project / "app/data.mjs").read_bytes() == before
