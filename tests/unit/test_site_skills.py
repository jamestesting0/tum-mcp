from pathlib import Path

import pytest
import yaml

from tum_mcp.clients import install_client
from tum_mcp.errors import CampusError
from tum_mcp.skill_validation import validate_skills
from tum_mcp.skills import customize_skill, export_pack


def test_pack_contains_reading_and_study_workflows_with_valid_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a fresh skill configuration.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    # When the exported site pack is validated against the running tool inventory.
    report = validate_skills()
    # Then the reading, study and audio workflows are discoverable and references resolve.
    assert set(report.checked_skills) == {
        "read-content",
        "sync-course",
        "prepare-study",
        "prepare-exercises",
        "prepare-exams",
        "publish-course",
    }
    assert report.errors == () and report.reference_characters > 0
    assert report.activation_evaluated is False


def test_legacy_personal_overrides_are_preserved_and_require_review_before_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an older user customization whose intent cannot be inferred safely.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    legacy = tmp_path / "config/skills/tum-artemis-local-fix/SKILL.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("personal customization to preserve", encoding="utf-8")
    destination = tmp_path / "export"
    # When the consolidated pack is exported.
    with pytest.raises(CampusError, match="Legacy skill customizations"):
        export_pack(destination)
    # Then the override stays intact and an incomplete new pack is not created.
    assert legacy.read_text(encoding="utf-8") == "personal customization to preserve"
    assert not destination.exists()


def test_claude_respects_a_users_explicit_only_site_skill_preference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a user who opts out of automatic Artemis skill invocation.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    custom = customize_skill("read-content")
    policy = custom / "agents/openai.yaml"
    policy.write_text("policy:\n  allow_implicit_invocation: false\n", encoding="utf-8")
    # When the Claude adapter installs the site skill.
    install_client("claude", tmp_path / "profile")
    # Then the equivalent host invocation control is preserved.
    entry = tmp_path / "profile/.claude/skills/read-content/SKILL.md"
    frontmatter = yaml.safe_load(entry.read_text(encoding="utf-8").split("---", 2)[1])
    assert frontmatter["disable-model-invocation"] is True


@pytest.mark.parametrize("name", ["prepare-study", "prepare-exercises", "audio-notes"])
def test_local_study_workflow_does_not_require_a_campus_server(name: str) -> None:
    from tum_mcp.skills import bundled, implicit_invocation

    skill = bundled() / name
    policy = yaml.safe_load((skill / "agents/openai.yaml").read_text(encoding="utf-8"))
    assert implicit_invocation(skill)
    assert not policy.get("dependencies", {}).get("tools", [])


def test_every_bundled_skill_has_complete_host_display_metadata() -> None:
    # Codex prefixes "<Plugin>: " to skills without a display name, so every skill needs one.
    from tum_mcp.skill_catalog import BUNDLED_SKILLS
    from tum_mcp.skills import bundled

    for name in BUNDLED_SKILLS:
        metadata = yaml.safe_load((bundled() / name / "agents/openai.yaml").read_text("utf-8"))
        interface = metadata.get("interface", {})
        assert interface.get("display_name") == name.replace("-", " ").title(), name
        assert interface.get("short_description", "").strip(), name
        assert f"${name}" in interface.get("default_prompt", ""), name
        assert metadata["policy"]["allow_implicit_invocation"] is True, name


def test_activation_cases_have_unique_ids_and_current_workflow_labels() -> None:
    from importlib.resources import files

    from tum_mcp.evaluations import Corpus
    from tum_mcp.skill_catalog import BUNDLED_SKILLS

    cases = Corpus.model_validate_json(
        (files("tum_mcp") / "bundled/activation-cases.json").read_bytes()
    ).root
    assert len({case.id for case in cases}) == len(cases)
    assert {case.target_skill for case in cases} <= set(BUNDLED_SKILLS)
    assert {case.expected_skill for case in cases} <= {*BUNDLED_SKILLS, None}
    assert {case.partition for case in cases} == {"development", "held_out"}


@pytest.mark.parametrize("name", ["codex", "claude"])
def test_audio_workflow_installs_with_its_complete_reference_bundle(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.skills import bundled

    # Given a fresh client profile and the canonical audio skill bundle.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    from tum_mcp.extensions import set_audio_notes

    set_audio_notes(True)
    source = bundled() / "audio-notes"
    # When the host installs its managed study skills.
    install_client(name, home)
    # Then the audio skill is discoverable and its linked resources survive export.
    entries = list(home.rglob("audio-notes/SKILL.md"))
    assert len(entries) == 1
    entry = entries[0]
    frontmatter = yaml.safe_load(entry.read_text(encoding="utf-8").split("---", 2)[1])
    assert frontmatter["name"] == "audio-notes"
    expected = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    installed = {
        path.relative_to(entry.parent) for path in entry.parent.rglob("*") if path.is_file()
    }
    assert installed == expected
    for relative in expected - {Path("SKILL.md")}:
        assert (entry.parent / relative).read_bytes() == (source / relative).read_bytes()
