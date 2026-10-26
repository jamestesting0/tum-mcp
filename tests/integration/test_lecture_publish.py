import json
from pathlib import Path

import pytest
import test_lecture_build as lecture_fixtures
import test_study_publish as publish_fixtures

from tum_mcp.errors import CampusError
from tum_mcp.study_build import build
from tum_mcp.study_github import GitHub
from tum_mcp.study_publish import configure, publish
from tum_mcp.study_publish_models import Publication, course_identity
from tum_mcp.study_publish_site import MARKER, SITE_FILES, commit_site, export_site
from tum_mcp.study_store import load_state

lecture_project = lecture_fixtures.lecture_project
github = publish_fixtures.github


def data(site):
    return json.loads(site["data.mjs"].removeprefix(b"const data = ").split(b";\ndata.hosted")[0])


@pytest.mark.parametrize(
    "include_exercises,include_lectures",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_scope_projection_and_referenced_figures_only(
    lecture_project: Path, include_exercises: bool, include_lectures: bool
) -> None:
    build(lecture_project, publish=False)
    (lecture_project / "study/unrelated.png").write_bytes(b"PRIVATE_FILE")
    (lecture_project / ".tum-mcp/comments.json").write_text("PRIVATE_COMMENT")
    site = export_site(
        lecture_project, include_exercises=include_exercises, include_lectures=include_lectures
    )
    payload = data(site)
    assert ("lectures" in payload) == include_lectures
    assert ("exercises" in payload) == include_exercises
    assert any(name.startswith("lecture-assets/") for name in site) == include_lectures
    assert all(name in SITE_FILES or name.startswith("lecture-assets/") for name in site)
    assert not any(b"PRIVATE_" in value for value in site.values())
    if not include_lectures:
        assert b"Synthetic lecture: why FIFO" not in site["data.mjs"]
    assert len(site) + 1 <= 100


def test_excluded_lecture_math_source_and_content_are_removed(lecture_project: Path) -> None:
    from tum_mcp.study_models import Resource, ResourceState
    from tum_mcp.study_store import digest

    root = lecture_project
    state = load_state(root)
    path = root / "materials/content/material-lecture-only.md"
    path.write_bytes(b"LECTURE_ONLY")
    source = ResourceState(
        resource=Resource(
            key="lecture-only",
            binding=state.course.bindings[0].key,
            kind="content",
            title="LECTURE_ONLY_SOURCE",
            url="https://example.invalid/LECTURE_ONLY_URL",
            locator="LECTURE_ONLY_LOCATOR",
            revision="1",
        ),
        path=path.relative_to(root).as_posix(),
        sha256=digest(path.read_bytes()),
        status="current",
    )
    (root / ".tum-mcp/state.json").write_text(
        state.model_copy(update={"resources": (*state.resources, source)}).model_dump_json()
    )
    notes = root / "study/lectures.json"
    value = json.loads(notes.read_text())
    lecture = value["lectures"][0]
    lecture["sources"] = [{"key": "lecture-only", "sha256": source.sha256}]
    lecture["overview"] += r" LECTURE_ONLY_TEXT \(\mathrm{LECTUREONLYMATH}\)"
    for block in lecture["sections"][0]["blocks"]:
        block["sources"] = ["lecture-only"]
    for evidence in value["evidence"]:
        evidence.update(source_key="lecture-only", source_sha256=source.sha256)
    notes.write_text(json.dumps(value))
    build(root, publish=False)
    assert not any(
        b"LECTURE_ONLY" in value or b"LECTUREONLYMATH" in value
        for value in export_site(root).values()
    )
    included = export_site(root, include_lectures=True)
    assert (
        b"LECTURE_ONLY_SOURCE" in included["data.mjs"]
        and b"LECTUREONLYMATH" in included["data.mjs"]
    )


def test_old_config_defaults_and_include_exclude_remote_asset_lifecycle(
    lecture_project: Path, github
) -> None:
    root = lecture_project
    build(root, publish=False)
    selected = configure(root)
    assert not selected.include_lectures
    publish(root, wait_seconds=0, rebuild=False)
    assert not any(name.startswith("lecture-assets/") for name in github.files(selected.repository))
    selected = configure(root, include_lectures=True)
    publish(root, wait_seconds=0, rebuild=False)
    assert any(name.startswith("lecture-assets/") for name in github.files(selected.repository))
    github.edit(selected.repository, "personal.txt", b"Keep my unrelated file")
    selected = configure(root, include_lectures=False)
    publish(root, wait_seconds=0, rebuild=False)
    files = github.files(selected.repository)
    assert files["personal.txt"] == b"Keep my unrelated file"
    assert not any(name.startswith("lecture-assets/") for name in files)
    assert not any(
        name.startswith("lecture-assets/") for name in json.loads(files[MARKER])["files"]
    )
    previous = selected.model_dump()
    previous.pop("include_lectures")
    assert not Publication.model_validate(previous).include_lectures


def test_excluded_notes_only_and_missing_figure_fail_without_remote_writes(
    lecture_project: Path, github
) -> None:
    root = lecture_project
    (root / "study/content.json").unlink()
    (root / "study/exercises.json").unlink()
    build(root, publish=False)
    with pytest.raises(CampusError, match="Explicitly include"):
        export_site(root)
    assert data(export_site(root, include_lectures=True))["workspaces"] == ["lectures"]
    for image in (root / "study/lecture-assets").iterdir():
        image.unlink()
    with pytest.raises(CampusError, match="figure"):
        export_site(root, include_lectures=True)
    with pytest.raises(CampusError, match="figure"):
        configure(root, include_lectures=True)
    assert github.requests == []


@pytest.mark.parametrize("failure", ["files", "bytes", "path"])
def test_export_limits_reject_before_remote_read_or_write(
    lecture_project: Path, github, failure: str
) -> None:
    identity = course_identity(load_state(lecture_project).course)
    site = {"data.mjs": b"x"}
    if failure == "files":
        site.update({f"lecture-assets/{index:064x}.png": b"x" for index in range(99)})
    elif failure == "bytes":
        site["data.mjs"] = b"x" * (16 * 1024**2)
    else:
        site["lecture-assets/../../private.png"] = b"x"
    publication = Publication(
        course_identity=identity,
        repository="test/private",
        public_site=True,
        branch="main",
        commit="0" * 40,
    )
    with pytest.raises(CampusError):
        commit_site(GitHub.discover(), publication, site)
    assert github.requests == []
