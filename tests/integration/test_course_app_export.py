import json
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_build import build
from tum_mcp.study_models import Resource, ResourceState
from tum_mcp.study_publish_projection import project as project_public_data
from tum_mcp.study_publish_site import SITE_FILES, export_site
from tum_mcp.study_store import digest, load_state


def test_all_exercise_content_is_exported_without_source_or_private_file_canaries(
    exercise_project: Path,
) -> None:
    root = exercise_project
    state = load_state(root)
    secret = b"PRIVATE_SOURCE_BYTES"
    path = root / "materials/exercises/material-ex-only.md"
    path.write_bytes(secret)
    resource = Resource(
        key="ex-only",
        binding=state.course.bindings[0].key,
        kind="exercise",
        title="PRIVATE_SOURCE_TITLE",
        url="https://example.invalid/PRIVATE_URL",
        locator="PRIVATE_LOCATOR",
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
    exercise["steps"][0]["hints"].append(r"PUBLIC_HINT \(\mathrm{PUBLICMATH}\)")

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
        block["paragraphs"].append("PUBLIC_STATEMENT_OR_SOLUTION")
    file.write_text(json.dumps(content))
    (root / ".tum-mcp/comments.json").write_text("PRIVATE_COMMENT")
    (root / "study/unrelated.json").write_text("PRIVATE_RESPONSE")
    build(root, publish=False)
    combined = export_site(root)
    assert set(combined) == set(SITE_FILES)
    assert b"PUBLIC_HINT" in combined["data.mjs"]
    assert b"PUBLIC_STATEMENT_OR_SOLUTION" in combined["data.mjs"]
    assert b"PUBLICMATH" in combined["data.mjs"]
    assert not any(b"PRIVATE_" in value for value in combined.values())
    (root / "study/content.json").unlink()
    build(root, publish=False)
    exported = export_site(root)["data.mjs"].decode()
    payload = json.loads(exported.removeprefix("const data = ").split(";\ndata.hosted")[0])
    assert payload["workspaces"] == ["exercises"]
    assert payload["sources"] == {}


def test_hosted_preparation_does_not_disclose_source_inventory(project: Path) -> None:
    # Given a local preparation queue containing both published and unselected sources.
    payload = json.loads(
        (project / "study/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )
    selected = payload["units"][0]["sources"][0]["key"]
    public = {"source": selected, "title": "Published source", "outcomes": []}
    private = {"source": "not-published", "title": "UNSELECTED_PRIVATE_TITLE", "outcomes": []}
    authoring = public | {"title": "PRIVATE_AUTHORING_STATE"}
    payload["studyPreparation"] = {
        "pending": [public, private],
        "unrecorded": [authoring],
        "enrichmentPending": [authoring],
    }
    # When the same native publication projection selects public workspaces.
    result = project_public_data(payload)
    # Then the public artifact contains no local preparation queue or document inventory.
    assert "studyPreparation" not in result
    assert "UNSELECTED_PRIVATE_TITLE" not in json.dumps(result)
    assert "PRIVATE_AUTHORING_STATE" not in json.dumps(result)


@pytest.mark.parametrize("changed", ["source_metadata", "source_version"])
def test_modified_generated_provenance_is_rejected_before_it_is_stripped(
    project: Path, changed: str
) -> None:
    path = project / "study/data.mjs"
    payload = json.loads(path.read_bytes().removeprefix(b"export default ").removesuffix(b";\n"))
    if changed == "source_metadata":
        next(iter(payload["sources"].values()))["title"] = "PRIVATE_TAMPER"
    else:
        payload["units"][0]["sources"][0]["sha256"] = "0" * 64
    path.write_bytes(b"export default " + json.dumps(payload).encode() + b";\n")
    with pytest.raises(CampusError) as error:
        export_site(project)
    assert error.value.code == Code.STALE_RESULT


@pytest.mark.parametrize(
    "path", ["figures/../private.png", "figures/private.json", "../private.png"]
)
def test_static_asset_allowlist_still_rejects_non_image_or_escaping_paths(
    project: Path, path: str
) -> None:
    from tum_mcp.study_publish_models import course_identity
    from tum_mcp.study_publish_site import preflight

    output = export_site(project)
    output[path] = b"PRIVATE"
    with pytest.raises(CampusError, match="unmanaged"):
        preflight(output, course_identity(load_state(project).course))
