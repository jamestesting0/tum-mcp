import json
from pathlib import Path

import pytest
import test_lecture_build as lecture_fixtures
import test_study_publish as publish_fixtures
from documents import content_file

from tum_mcp.course.app.build import build
from tum_mcp.course.app.github import GitHub
from tum_mcp.course.app.publish import configure, publish
from tum_mcp.course.app.publish_models import Publication, course_identity
from tum_mcp.course.app.publish_site import MARKER, SITE_FILES, commit_site, export_site
from tum_mcp.course.project.store import load_state
from tum_mcp.errors import CampusError

lecture_project = lecture_fixtures.lecture_project
github = publish_fixtures.github


def data(site):
    return json.loads(site["data.mjs"].removeprefix(b"const data = ").split(b";\ndata.hosted")[0])


@pytest.mark.parametrize(
    "selected", [("study",), ("exercises",), ("lectures",), ("study", "exercises", "lectures")]
)
def test_scope_projection_and_referenced_thumbnails_only(
    lecture_project: Path, selected: tuple[str, ...]
) -> None:
    for workspace in ("study", "exercises", "lectures"):
        if workspace not in selected:
            content_file(lecture_project, workspace).unlink()
    build(lecture_project, publish=False)
    (lecture_project / "app/unrelated.png").write_bytes(b"PRIVATE_FILE")
    (lecture_project / ".tum-mcp/comments.json").write_text("PRIVATE_COMMENT", encoding="utf-8")
    site = export_site(lecture_project)
    payload = data(site)
    assert payload["workspaces"] == list(selected)
    assert any(name.startswith("lecture-assets/") for name in site) == ("lectures" in selected)
    assert all(name in SITE_FILES or name.startswith("lecture-assets/") for name in site)
    assert not any(b"PRIVATE_" in value for value in site.values())
    if "lectures" not in selected:
        assert b"Synthetic lecture: why FIFO" not in site["data.mjs"]
    assert len(site) + 1 <= 100


def test_lecture_content_math_and_canonical_links_survive_without_source_metadata(
    lecture_project: Path,
) -> None:
    from tum_mcp.course.project.models import Resource, ResourceState
    from tum_mcp.course.project.store import digest

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
        state.model_copy(update={"resources": (*state.resources, source)}).model_dump_json(),
        encoding="utf-8",
    )
    notes = content_file(root, "lectures")
    value = json.loads(notes.read_text(encoding="utf-8"))
    lecture = value["lectures"][0]
    lecture["sources"] = [{"key": "lecture-only", "sha256": source.sha256}]
    lecture["summary"] += r" LECTURE_ONLY_TEXT \(\mathrm{LECTUREONLYMATH}\)"
    for entry in lecture["notes"] + lecture["highlights"]:
        entry["sources"] = ["lecture-only"]
    for evidence in value["evidence"]:
        evidence.update(source_key="lecture-only", source_sha256=source.sha256)
    notes.write_text(json.dumps(value), encoding="utf-8")
    build(root, publish=False)
    included = export_site(root)
    assert b"LECTURE_ONLY_TEXT" in included["data.mjs"]
    assert b"LECTUREONLYMATH" in included["data.mjs"]
    for private in (
        b"LECTURE_ONLY_SOURCE",
        b"LECTURE_ONLY_URL",
        b"LECTURE_ONLY_LOCATOR",
        b'"evidence"',
        b'"sha256"',
        b'"pages"',
    ):
        assert private not in included["data.mjs"]
    public = data(included)
    assert public["sources"] == {
        "live-1-1": {
            "title": lecture["title"],
            "url": "https://example.invalid/lectures/synthetic",
        }
    }
    published = public["lectures"]["lectures"][0]
    assert published["notes"][0]["recording_source"] == "live-1-1"
    assert published["notes"][0]["url"].endswith("?t=300")
    assert [item["url"].rsplit("?", 1)[1] for item in published["highlights"]] == ["t=20", "t=120"]


def test_deleted_lecture_assets_leave_the_same_repository_without_erasing_unrelated_files(
    lecture_project: Path, github
) -> None:
    root = lecture_project
    build(root, publish=False)
    selected = configure(root)
    publish(root, wait_seconds=0, rebuild=False)
    assert any(name.startswith("lecture-assets/") for name in github.files(selected.repository))
    github.edit(selected.repository, "personal.txt", b"Keep my unrelated file")
    path = content_file(root, "lectures")
    notes = json.loads(path.read_bytes())
    removed = notes["lectures"][0]["highlights"][-1]["thumbnail"]["asset"]
    lecture_fixtures.remove_second_highlight(notes)
    path.write_text(json.dumps(notes))
    build(root, publish=False)
    publish(root, wait_seconds=0, rebuild=False)
    files = github.files(selected.repository)
    assert files["personal.txt"] == b"Keep my unrelated file"
    assert removed not in files
    assert removed not in json.loads(files[MARKER])["files"]


def test_lecture_only_exports_and_missing_images_fail_without_remote_writes(
    lecture_project: Path, github
) -> None:
    root = lecture_project
    (content_file(root, "study")).unlink()
    (content_file(root, "exercises")).unlink()
    build(root, publish=False)
    assert data(export_site(root))["workspaces"] == ["lectures"]
    for image in (root / "app/lecture-assets").iterdir():
        image.unlink()
    with pytest.raises(CampusError, match="thumbnail"):
        export_site(root)
    with pytest.raises(CampusError, match="thumbnail"):
        configure(root)
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


def test_note_images_export_without_highlights_or_private_provenance(lecture_project: Path) -> None:
    path = content_file(lecture_project, "lectures")
    value = json.loads(path.read_bytes())
    lecture = value["lectures"][0]
    first = lecture["highlights"][0]
    lecture["notes"][0]["image"] = first["thumbnail"] | {"alt": "A three-vertex path."}
    lecture["notes"][0]["evidence"] += first["evidence"]
    lecture["highlights"] = []
    used = set(lecture["notes"][0]["evidence"])
    value["evidence"] = [item for item in value["evidence"] if item["key"] in used]
    path.write_text(json.dumps(value))
    build(lecture_project, publish=False)
    included = export_site(lecture_project)
    assert first["thumbnail"]["asset"] in included
    assert data(included)["lectures"]["lectures"][0]["notes"][0]["image"]["alt"]
    image = data(included)["lectures"]["lectures"][0]["notes"][0]["image"]
    assert "evidence" not in image and "sha256" not in image
