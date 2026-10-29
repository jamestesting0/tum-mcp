import json
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.study_build import build
from tum_mcp.study_models import Resource, ResourceState
from tum_mcp.study_publish_site import SITE_FILES, export_site
from tum_mcp.study_store import digest, load_state


def test_excluded_exercises_leave_no_statement_hint_solution_math_or_source_canary(
    exercise_project: Path,
) -> None:
    root = exercise_project
    state = load_state(root)
    secret = b"EXCLUDED_SOURCE_BYTES"
    path = root / "materials/exercises/material-ex-only.md"
    path.write_bytes(secret)
    resource = Resource(
        key="ex-only",
        binding=state.course.bindings[0].key,
        kind="exercise",
        title="EXCLUDED_SOURCE_TITLE",
        url="https://example.invalid/EXCLUDED_URL",
        locator="EXCLUDED_LOCATOR",
        revision="1",
    )
    added = ResourceState(
        resource=resource,
        path=path.relative_to(root).as_posix(),
        sha256=digest(secret),
        status="current",
    )
    (root / ".tum-mcp/state.json").write_text(
        state.model_copy(update={"resources": (*state.resources, added)}).model_dump_json(),
        encoding="utf-8",
    )
    file = root / "study/exercises.json"
    content = json.loads(file.read_bytes())
    exercise = content["sets"][0]["exercises"][0]
    exercise["sources"] = [{"key": "ex-only", "sha256": digest(secret)}]
    exercise["steps"][0]["hints"].append(r"EXCLUDED_HINT \(\mathrm{EXCLUDED_MATH}\)")

    def blocks(value: object) -> list[dict]:
        if isinstance(value, list):
            return [block for item in value for block in blocks(item)]
        if not isinstance(value, dict):
            return []
        own = [value] if "kind" in value and isinstance(value.get("sources"), list) else []
        return own + blocks(list(value.values()))

    for block in blocks(exercise):
        block["sources"] = ["ex-only"]
    for block in (
        *exercise["statement"],
        *(b for a in exercise["solution"]["answers"] for b in a["blocks"]),
    ):
        block["paragraphs"].append("EXCLUDED_STATEMENT_OR_SOLUTION")
    file.write_text(json.dumps(content))
    (root / ".tum-mcp/comments.json").write_text("PRIVATE_COMMENT")
    (root / "study/unrelated.json").write_text("PRIVATE_RESPONSE")
    build(root, publish=False)
    study = export_site(root)
    assert set(study) == set(SITE_FILES)
    assert not any(b"EXCLUDED_" in value or b"PRIVATE_" in value for value in study.values())
    assert b'"workspaces": ["study"]' in study["data.mjs"]
    combined = export_site(root, include_exercises=True)
    assert b"EXCLUDED_HINT" in combined["data.mjs"]
    assert not any(b"PRIVATE_" in value for value in combined.values())
    (root / "study/content.json").unlink()
    build(root, publish=False)
    with pytest.raises(CampusError, match="Explicitly include"):
        export_site(root)
    exported = export_site(root, include_exercises=True)["data.mjs"].decode()
    payload = json.loads(exported.removeprefix("const data = ").split(";\ndata.hosted")[0])
    assert payload["workspaces"] == ["exercises"]
    # A published citation names its source but never the stored local copy.
    assert all("file" not in source for source in payload["sources"].values())
