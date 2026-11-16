"""Source lifecycle tests use local bytes and never a campus connection."""

import json
from pathlib import Path

import pytest
from documents import content_file
from knowledge_fixture import knowledge_project
from knowledge_lecture_fixture import real_cached_lecture

from tum_mcp.course.memory.evidence import EvidenceChecks
from tum_mcp.course.memory.store import read_inputs
from tum_mcp.course.project.paths import app_path
from tum_mcp.course.project.store import private_path
from tum_mcp.errors import CampusError, Code

pytestmark = pytest.mark.usefixtures("lecture_extension")


def test_unkeyed_and_repeated_passages_have_only_stable_owner_anchors(tmp_path: Path):
    from tum_mcp.course.memory.projection import project

    root = knowledge_project(tmp_path)
    path = content_file(root, "study")
    value = json.loads(path.read_bytes())
    blocks = value["units"][0]["blocks"]
    blocks.append(dict(blocks[0]))
    value["units"][1]["blocks"][0].pop("key", None)
    path.write_text(json.dumps(value))
    # This native schema already rejects duplicate passage keys; preserve that gate.
    with pytest.raises(CampusError, match="Invalid app/study/course.json"):
        read_inputs(root)
    blocks.pop()
    blocks[0].pop("key")
    path.write_text(json.dumps(value))
    graph = project(read_inputs(root))
    assert "study/unit/observer" in graph.nodes
    assert "study/unit/observer/block/observer-definition" not in graph.nodes
    assert any(issue.code == "missing_reference" for issue in graph.issues)


def test_saved_packets_never_enter_site_exports(tmp_path: Path):
    from tum_mcp.course.app.build import build
    from tum_mcp.course.app.publish_site import export_site
    from tum_mcp.course.memory.query import context

    root = knowledge_project(tmp_path)
    packet = context(root, concept="observer") | {"note": "PRIVATE_PACKET_SENTINEL"}
    private_path(root, "context.json").write_text(json.dumps(packet))
    build(root, publish=False)
    exported = b"".join(export_site(root).values())
    assert b"PRIVATE_PACKET_SENTINEL" not in exported


def files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("layout", [("app", ".tum-mcp")])
def test_snapshot_is_read_only(tmp_path: Path, layout) -> None:
    root = knowledge_project(tmp_path, layout)
    before = files(root)
    inputs = read_inputs(root)
    assert inputs.workspaces == ("study", "exercises", "exam", "lectures")
    checks = EvidenceChecks(inputs)
    assert all(checks.source(s).current for s in inputs.study.units[0].sources)
    assert checks.lecture("observer-lecture").current
    assert len(inputs.reader.verify()) == 64
    assert files(root) == before


@pytest.mark.parametrize("change", ["authored", "new-decisions", "source"])
def test_snapshot_detects_changes_between_read_and_return(tmp_path: Path, change: str) -> None:
    root = knowledge_project(tmp_path)
    inputs = read_inputs(root)
    EvidenceChecks(inputs).source(inputs.study.units[0].sources[0])
    match change:
        case "authored":
            path = content_file(root, "study")
            value = json.loads(path.read_bytes())
            value["introduction"] += " Changed."
            path.write_text(json.dumps(value), encoding="utf-8")
        case "new-decisions":
            private_path(root, "links.json").write_text("{}", encoding="utf-8")
        case "source":
            path = root / inputs.resources["slides"].path
            path.write_bytes(path.read_bytes().replace(b"Observer", b"Strategy"))
    with pytest.raises(CampusError) as error:
        inputs.reader.verify()
    assert error.value.code in {Code.STALE_RESULT, Code.WORKSPACE_CONFLICT}


def test_evidence_hashes_actual_bytes_not_inventory_generation(tmp_path: Path) -> None:
    root = knowledge_project(tmp_path)
    inputs = read_inputs(root)
    version = inputs.study.units[0].sources[0]
    path = root / inputs.resources[version.key].path
    original = path.read_bytes()
    path.write_bytes(original.replace(b"Observer", b"Strategy"))
    checks = EvidenceChecks(read_inputs(root))
    assert checks.source(version).state == "stale"
    path.write_bytes(original)
    assert EvidenceChecks(read_inputs(root)).source(version).current


@pytest.mark.parametrize("change", ["malformed", "scope", "symlink"])
def test_snapshot_boundary_errors_preserve_private_inputs(tmp_path: Path, change: str) -> None:
    root = knowledge_project(tmp_path)
    match change:
        case "malformed":
            app_path(root, "study/course.json").write_text("PRIVATE_SENTINEL", encoding="utf-8")
        case "scope":
            path = content_file(root, "exercises")
            value = json.loads(path.read_bytes()) | {"course_key": "another-course"}
            path.write_text(json.dumps(value), encoding="utf-8")
        case "symlink":
            path = app_path(root, "study/course.json")
            path.rename(root / "saved.json")
            try:
                path.symlink_to(root / "saved.json")
            except OSError:
                pytest.skip("This host does not permit synthetic symlinks.")
    before = files(root)
    with pytest.raises(CampusError) as error:
        read_inputs(root)
    assert "PRIVATE_SENTINEL" not in str(error.value)
    assert files(root) == before


def test_lecture_snapshot_observes_receipt_transcript_and_absent_progress(tmp_path: Path) -> None:
    root = real_cached_lecture(tmp_path)
    inputs = read_inputs(root)
    assert EvidenceChecks(inputs).lecture("observer-lecture").current
    inputs.reader.verify()
    cache = private_path(root, "lectures/live-42-11")
    (cache / "progress.json").write_text(
        json.dumps({"metadata_revision": "c" * 64, "stage": "interrupted"}), encoding="utf-8"
    )
    with pytest.raises(CampusError, match="changed"):
        inputs.reader.verify()
    assert not EvidenceChecks(read_inputs(root)).lecture("observer-lecture").current
    (cache / "progress.json").unlink()
    (cache / "transcript.json").write_bytes(b"[ ]")
    assert not EvidenceChecks(read_inputs(root)).lecture("observer-lecture").current


@pytest.mark.parametrize("failure", ["source-frame", "forged-crop"])
def test_lecture_snapshot_checks_original_frames_and_verified_crops(
    tmp_path: Path, failure: str
) -> None:
    root = real_cached_lecture(tmp_path, with_frame=True)
    before = files(root)
    inputs = read_inputs(root)
    assert EvidenceChecks(inputs).lecture("observer-lecture").current
    inputs.reader.verify()
    assert files(root) == before
    if failure == "source-frame":
        path = next(private_path(root, "lectures/live-42-11/frames").glob("*.png"))
        path.write_bytes(b"changed original frame")
    else:
        path = content_file(root, "lectures")
        value = json.loads(path.read_bytes())
        thumbnail = value["lectures"][0]["highlights"][0]["thumbnail"]
        thumbnail["sha256"] = "f" * 64
        thumbnail["asset"] = "lecture-assets/" + "f" * 64 + ".png"
        path.write_text(json.dumps(value), encoding="utf-8")
    assert not EvidenceChecks(read_inputs(root)).lecture("observer-lecture").current
