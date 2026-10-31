import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.audio_content import AudioCoverage, AudioPlan
from tum_mcp.study_build import read_content
from tum_mcp.study_media import discover
from tum_mcp.study_store import load_state


def inventory(root: Path):
    return discover(root, load_state(root), read_content(root))


def manifest(root: Path) -> dict:
    return json.loads((root / "audio/manifest.json").read_bytes())


def save(root: Path, value: dict) -> None:
    (root / "audio/manifest.json").write_text(json.dumps(value), encoding="utf-8")


def test_discovery_binds_exact_bytes_and_is_read_only(media_audio: Path) -> None:
    before = {p.relative_to(media_audio): p.stat().st_mtime_ns for p in media_audio.rglob("*")}
    found = inventory(media_audio)
    item = found.items[0]
    assert not found.invalid and not item.stale and not item.technical
    assert item.item == "audio/graphs" and item.structure["targets"] == ["study/bfs"]
    assert (
        item.projection["files"]["track"]
        == manifest(media_audio)["categories"]["graphs"]["track"]["sha256"]
    )
    assert len(item.revision) == 16
    value = manifest(media_audio)
    (media_audio / "audio/manifest.json").write_text(json.dumps(value, indent=4), encoding="utf-8")
    assert inventory(media_audio).items[0].revision == item.revision
    before.pop(Path("audio/manifest.json"))
    assert all((media_audio / path).stat().st_mtime_ns == time for path, time in before.items())


@pytest.mark.parametrize(
    "failure", ["same_size", "missing", "symlink", "field", "course", "traversal"]
)
def test_invalid_optional_audio_preserves_other_course_state(
    media_audio: Path,
    tmp_path: Path,
    failure: str,
) -> None:
    value = manifest(media_audio)
    receipt = value["categories"]["graphs"]
    track = media_audio / "audio" / receipt["track"]["path"]
    match failure:
        case "same_size":
            data = track.read_bytes()
            track.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        case "missing":
            track.unlink()
        case "symlink":
            external = tmp_path / "external.m4a"
            external.write_bytes(track.read_bytes())
            track.unlink()
            track.symlink_to(external)
        case "field":
            receipt.pop("voice")
            save(media_audio, value)
        case "course":
            value["course_key"] = "other-course"
            save(media_audio, value)
        case "traversal":
            receipt["validation"]["path"] = "../outside.json"
            save(media_audio, value)
    found = inventory(media_audio)
    assert found.invalid and not found.items
    assert read_content(media_audio).course_key == load_state(media_audio).course.key


def test_chapters_are_checked_even_when_their_receipt_digest_was_updated(media_audio: Path) -> None:
    value = manifest(media_audio)
    receipt = value["categories"]["graphs"]
    path = media_audio / "audio" / receipt["chapters"]["path"]
    data = json.dumps(
        [
            {"key": "late", "title": "Late", "start": 1, "end": 2},
            {"key": "queue", "title": "Queue", "start": 0, "end": 1},
        ]
    ).encode()
    path.write_bytes(data)
    receipt["chapters"].update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    save(media_audio, value)
    assert inventory(media_audio).invalid


def test_core_meaning_changes_review_identity_but_explore_does_not(media_audio: Path) -> None:
    original = inventory(media_audio).items[0]
    path = media_audio / "app/content.json"
    value = json.loads(path.read_bytes())
    unit = next(u for u in value["units"] if u["key"] == "bfs")
    unit["explore"] = [
        {
            "key": "history",
            "title": "Optional history",
            "sources": unit["sources"],
            "blocks": [
                {
                    "kind": "text",
                    "key": "context",
                    "paragraphs": ["Optional context."],
                    "sources": [unit["sources"][0]["key"]],
                }
            ],
        }
    ]
    path.write_text(json.dumps(value), encoding="utf-8")
    assert inventory(media_audio).items[0].revision == original.revision
    unit["summary"] += " A new required condition."
    path.write_text(json.dumps(value), encoding="utf-8")
    current = inventory(media_audio).items[0]
    assert current.revision != original.revision and "teaching_changed" in current.stale


def test_pending_none_is_derived_from_actual_current_teaching(media_audio: Path) -> None:
    from tum_mcp.audio_content import AudioCategory

    receipt = manifest(media_audio)["categories"]["graphs"]
    category = {name: receipt[name] for name in AudioCategory.model_fields}
    plan = AudioPlan(
        course_key=load_state(media_audio).course.key,
        content_sha256="0" * 64,
        category_order=["graphs"],
        categories={"graphs": {**category, "pending": "none"}},
    )
    (media_audio / "audio/plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    assert inventory(media_audio).pending == []
    path = media_audio / "app/content.json"
    value = json.loads(path.read_bytes())
    next(u for u in value["units"] if u["key"] == "bfs")["summary"] += " Changed."
    path.write_text(json.dumps(value), encoding="utf-8")
    assert inventory(media_audio).pending == [{"item": "audio/graphs", "reason": "changed"}]


@pytest.mark.parametrize("mode", ["study_required", "missing"])
def test_nonspoken_coverage_must_disclose_its_specific_dependency(
    media_audio: Path,
    mode: str,
) -> None:
    entry = manifest(media_audio)["categories"]["graphs"]["coverage"][0]
    with pytest.raises(ValidationError):
        AudioCoverage.model_validate({**entry, "mode": mode})


def test_byte_and_profile_changes_affect_only_their_category(media_audio: Path) -> None:
    value = manifest(media_audio)
    first = value["categories"]["graphs"]
    second = json.loads(json.dumps(first))
    second.update(key="second", stem="02_other-revision")
    for name in ("script", "track", "chapters"):
        file = second[name]
        old = media_audio / "audio" / file["path"]
        file["path"] = file["path"].replace("01_graph-revision", second["stem"])
        (media_audio / "audio" / file["path"]).write_bytes(old.read_bytes())
    value["categories"]["second"] = second
    save(media_audio, value)
    original = {item.item: item.revision for item in inventory(media_audio).items}
    first["voice"]["settings"]["speed"] = 1.1
    save(media_audio, value)
    current = {item.item: item.revision for item in inventory(media_audio).items}
    assert current["audio/graphs"] != original["audio/graphs"]
    assert current["audio/second"] == original["audio/second"]


def test_empty_optional_media_does_not_require_any_extension(media_audio: Path) -> None:
    (media_audio / "audio/manifest.json").unlink()
    found = inventory(media_audio)
    assert found.items == [] and found.pending == [] and found.invalid == []


def test_moved_unit_is_pending_without_renaming_or_overwriting_the_old_track(
    media_audio: Path,
) -> None:
    from tum_mcp.audio_content import AudioCategory, category_hash

    receipt = manifest(media_audio)["categories"]["graphs"]
    category = {name: receipt[name] for name in AudioCategory.model_fields}
    retired = {
        **category,
        "units": [],
        "coverage": [],
        "pending": "removed",
        "category_sha256": category_hash(category["title"], ()),
    }
    moved = {**category, "key": "moved", "stem": "02_moved-graphs", "pending": "none"}
    plan = AudioPlan(
        course_key=load_state(media_audio).course.key,
        content_sha256="0" * 64,
        category_order=["moved"],
        categories={"graphs": retired, "moved": moved},
    )
    track = media_audio / "audio" / receipt["track"]["path"]
    before = track.read_bytes()
    (media_audio / "audio/plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    found = inventory(media_audio)
    assert {entry["item"]: entry["reason"] for entry in found.pending} == {
        "audio/graphs": "removed",
        "audio/moved": "moved",
    }
    assert track.read_bytes() == before
