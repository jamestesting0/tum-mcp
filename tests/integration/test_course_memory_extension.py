"""Course Memory activation must not make retained metadata an implicit capability."""

import json
from pathlib import Path

import pytest
from knowledge_annotations import annotation, write_registry
from knowledge_fixture import knowledge_project
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.clients import install_client
from tum_mcp.errors import CampusError, Code
from tum_mcp.extension_selection import course_memory_enabled
from tum_mcp.skills import export_pack, inspect_skills
from tum_mcp.study_store import load_state, private_path


@pytest.fixture
def profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr("tum_mcp.updates.is_wsl", lambda: False)
    return home


def test_disabled_memory_refuses_context_before_reading_course(
    profile: Path, tmp_path: Path
) -> None:
    root = knowledge_project(tmp_path, workspaces=frozenset({"study"}))
    result = CliRunner().invoke(app, ["study", "context", str(root), "Observer"])
    assert result.exit_code != 0
    assert isinstance(result.exception, CampusError)
    assert result.exception.code == Code.ACTION_REQUIRED
    assert not private_path(root, "knowledge.json").exists()


def test_disabled_memory_cannot_break_native_reports_with_retained_invalid_files(
    profile: Path, tmp_path: Path
) -> None:
    root = knowledge_project(tmp_path, workspaces=frozenset({"study"}))
    sidecar = private_path(root, "knowledge.json")
    sidecar.write_text('{"PRIVATE_MEMORY_SENTINEL":')
    for section in ("structure", "review"):
        result = CliRunner().invoke(app, ["study", "report", str(root), "--section", section])
        assert result.exit_code == 0, result.output or repr(result.exception)
        assert section in json.loads(result.output)
    assert sidecar.read_text() == '{"PRIVATE_MEMORY_SENTINEL":'


@pytest.mark.parametrize("client", ["codex", "claude", "cursor", "antigravity", "generic"])
def test_memory_installs_only_when_selected_and_survives_client_refresh(
    profile: Path, tmp_path: Path, client: str
) -> None:
    install_client(client, profile, announce=False)
    assert not course_memory_enabled()
    assert "course-memory" not in {s["name"] for s in inspect_skills()}
    runner = CliRunner()
    installed = runner.invoke(app, ["install", "course-memory", "--json"])
    assert installed.exit_code == 0, installed.output or repr(installed.exception)
    assert json.loads(installed.output)["state"] == "enabled"
    refreshed = runner.invoke(app, ["update"])
    assert refreshed.exit_code == 0, refreshed.output or repr(refreshed.exception)
    assert course_memory_enabled()
    export_pack(tmp_path / "export")
    assert (tmp_path / "export/course-memory/references/knowledge.md").is_file()
    assert not (tmp_path / "export/prepare-study/references/knowledge.md").exists()
    status = json.loads(runner.invoke(app, ["study", "status", str(tmp_path / "new")]).output)
    assert status["course_memory"] is True and status["mode"] == "initialize"
    assert not (tmp_path / "new").exists()
    doctor = json.loads(runner.invoke(app, ["doctor", "--json"]).output)
    assert (
        next(e["state"] for e in doctor["extensions"] if e["label"] == "Course Memory") == "Enabled"
    )


def test_first_use_can_initialize_and_review_scoped_memory_without_a_course_rebuild(
    profile: Path, tmp_path: Path
) -> None:
    root = knowledge_project(tmp_path, workspaces=frozenset({"study"}))
    sidecar = private_path(root, "knowledge.json")
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", "course-memory"]).exit_code == 0
    native = runner.invoke(app, ["study", "context", str(root), "Observer"])
    assert native.exit_code == 0 and not sidecar.exists()
    state = load_state(root)
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "course_key": state.course.key,
                "semester": state.course.semester,
                "concepts": [],
                "assertions": [],
            }
        )
    )
    empty = json.loads(
        runner.invoke(app, ["study", "report", str(root), "--section", "knowledge"]).output
    )
    assert empty["knowledge"]["counts"]["assertions"] == {}
    write_registry(root, [annotation(root)])
    pending = json.loads(
        runner.invoke(app, ["study", "report", str(root), "--section", "knowledge"]).output
    )
    assert pending["knowledge"]["assertions"][0]["state"] == "candidate"
    # The fixture source explicitly teaches registration; this is a synthetic author review.
    write_registry(root, [annotation(root)], reviewed=True)
    packet = json.loads(
        runner.invoke(app, ["study", "context", str(root), "--concept", "observer"]).output
    )
    assert any(i["id"] == "study/unit/observer" for i in packet["items"])
    assert any(s.get("assertion") == "teaching" for p in packet["paths"] for s in p["steps"])
    assert not (root / "app/index.html").exists()


@pytest.mark.parametrize("changed", [False, True])
def test_uninstall_preserves_files_and_native_review_then_reinstall_checks_sources(
    profile: Path, tmp_path: Path, changed: bool
) -> None:
    root = knowledge_project(tmp_path, workspaces=frozenset({"study"}))
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", "course-memory"]).exit_code == 0
    write_registry(root, [annotation(root)], reviewed=True)
    sidecar = private_path(root, "knowledge.json")
    before = sidecar.read_bytes()
    review = json.loads(
        runner.invoke(app, ["study", "report", str(root), "--section", "review"]).output
    )["review"]["course"]
    private_path(root, "review.json").write_text(
        json.dumps(
            {
                "course_key": load_state(root).course.key,
                "reviews": [],
                "course": {
                    "revision": review["revision"],
                    "knowledge_revision": review["knowledge_revision"],
                    "reviewed_at": "2026-10-31",
                    "scores": {d: 3 for d in review["dimensions"]},
                },
            }
        )
    )
    removed = runner.invoke(app, ["uninstall", "course-memory", "--json"])
    assert removed.exit_code == 0, removed.output or repr(removed.exception)
    assert not course_memory_enabled() and sidecar.read_bytes() == before
    assert not (profile / ".cursor/skills/course-memory").exists()
    native = json.loads(
        runner.invoke(app, ["study", "report", str(root), "--section", "review"]).output
    )["review"]["course"]
    assert native["status"] == "fresh" and native["revision"] == review["revision"]
    assert "knowledge_revision" not in native
    for arguments in (
        ["context", str(root), "Observer"],
        ["impact", str(root), "--source", "slides"],
        ["report", str(root), "--section", "knowledge"],
    ):
        result = runner.invoke(app, ["study", *arguments])
        assert (
            isinstance(result.exception, CampusError)
            and result.exception.code == Code.ACTION_REQUIRED
        )
    source = next(s for s in load_state(root).resources if s.resource.key == "slides")
    if changed:
        (root / source.path).write_bytes(
            (root / source.path).read_bytes() + b"\n% new synthetic release\n"
        )
    assert runner.invoke(app, ["install", "course-memory"]).exit_code == 0
    audit = json.loads(
        runner.invoke(app, ["study", "report", str(root), "--section", "knowledge"]).output
    )["knowledge"]
    assert audit["assertions"][0]["state"] == ("invalid" if changed else "current")
    packet = json.loads(
        runner.invoke(app, ["study", "context", str(root), "--concept", "observer"]).output
    )
    assert bool(packet["items"]) is not changed and sidecar.read_bytes() == before


def test_source_sync_requires_content_and_semantic_review_before_reactivation(
    profile: Path, tmp_path: Path
) -> None:
    root = knowledge_project(tmp_path, workspaces=frozenset({"study"}))
    runner = CliRunner()
    assert runner.invoke(app, ["install", "course-memory"]).exit_code == 0
    write_registry(root, [annotation(root)], reviewed=True)
    sidecar = private_path(root, "knowledge.json")
    reviewed = sidecar.read_bytes()
    incoming = tmp_path / "incoming/slides.pdf"
    incoming.write_bytes(incoming.read_bytes() + b"\n% reviewed toy release\n")
    snapshot = tmp_path / "incoming/snapshot.json"
    document = json.loads(snapshot.read_bytes())
    next(r for r in document["resources"] if r["key"] == "slides")["revision"] = "2"
    snapshot.write_text(json.dumps(document))

    synced = runner.invoke(app, ["study", "sync", str(root), "--snapshot", str(snapshot)])
    assert synced.exit_code == 0, synced.output or repr(synced.exception)
    assert sidecar.read_bytes() == reviewed
    audit_args = ["study", "report", str(root), "--section", "knowledge"]
    audit = json.loads(runner.invoke(app, audit_args).output)["knowledge"]
    assert audit["assertions"][0]["state"] == "invalid"
    impact = json.loads(
        runner.invoke(app, ["study", "impact", str(root), "--source", "slides"]).output
    )
    assert "study/unit/observer" in impact["direct"]

    # Review the changed source and unchanged toy meaning before updating authored receipts.
    source = next(s for s in load_state(root).resources if s.resource.key == "slides")
    assert (root / source.path).read_bytes().endswith(b"% reviewed toy release\n")
    content = root / "app/content.json"
    value = json.loads(content.read_bytes())
    for unit in value["units"]:
        for segment in [unit, *unit.get("explore", [])]:
            for version in segment["sources"]:
                if version["key"] == "slides":
                    version["sha256"] = source.sha256
    content.write_text(json.dumps(value))
    # A source/owner refresh alone cannot reapprove the old semantic receipt.
    assert (
        json.loads(runner.invoke(app, audit_args).output)["knowledge"]["assertions"][0]["state"]
        != "current"
    )
    write_registry(root, [annotation(root)])
    assert (
        json.loads(runner.invoke(app, audit_args).output)["knowledge"]["assertions"][0]["state"]
        == "candidate"
    )
    write_registry(root, [annotation(root)], reviewed=True)
    assert (
        json.loads(runner.invoke(app, audit_args).output)["knowledge"]["assertions"][0]["state"]
        == "current"
    )


def test_customized_skill_cannot_keep_memory_active_after_uninstall(
    profile: Path, tmp_path: Path
) -> None:
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", "course-memory"]).exit_code == 0
    skill = profile / ".cursor/skills/course-memory/SKILL.md"
    skill.write_text(skill.read_text() + "\nPreserve my customization.\n")
    before = skill.read_bytes()
    removed = runner.invoke(app, ["uninstall", "course-memory"])
    assert removed.exit_code == 2
    assert not course_memory_enabled() and skill.read_bytes() == before
    result = runner.invoke(app, ["study", "context", str(tmp_path / "missing"), "Observer"])
    assert (
        isinstance(result.exception, CampusError) and result.exception.code == Code.ACTION_REQUIRED
    )


def test_named_uninstall_retries_after_customized_files_are_reconciled(profile: Path) -> None:
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", "course-memory"]).exit_code == 0
    skill = profile / ".cursor/skills/course-memory/SKILL.md"
    original = skill.read_bytes()
    skill.write_bytes(original + b"\nPreserve my customization.\n")
    assert runner.invoke(app, ["uninstall", "course-memory"]).exit_code == 2
    assert not course_memory_enabled()
    skill.write_bytes(original)
    assert runner.invoke(app, ["uninstall", "course-memory"]).exit_code == 0
    assert not skill.exists() and not course_memory_enabled()


def test_activation_conflict_leaves_memory_disabled_and_other_clients_unchanged(
    profile: Path,
) -> None:
    install_client("claude", profile, announce=False)
    install_client("cursor", profile, announce=False)
    conflict = profile / ".cursor/skills/course-memory/SKILL.md"
    conflict.parent.mkdir()
    conflict.write_text("Personal unrelated workflow")
    result = CliRunner().invoke(app, ["install", "course-memory"])
    assert result.exit_code != 0 and not course_memory_enabled()
    assert not (profile / ".claude/skills/course-memory").exists()
    assert conflict.read_text() == "Personal unrelated workflow"
