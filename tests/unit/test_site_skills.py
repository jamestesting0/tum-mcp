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
    # Then only the four workflows are discoverable and every reference resolves.
    assert set(report.checked_skills) == {
        "read-content",
        "init-study",
        "update-study",
        "prepare-study",
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
    legacy.write_text("personal customization to preserve")
    destination = tmp_path / "export"
    # When the consolidated pack is exported.
    with pytest.raises(CampusError, match="Legacy skill customizations"):
        export_pack(destination)
    # Then the override stays intact and an incomplete new pack is not created.
    assert legacy.read_text() == "personal customization to preserve"
    assert not destination.exists()


def test_claude_respects_a_users_explicit_only_site_skill_preference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a user who opts out of automatic Artemis skill invocation.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    custom = customize_skill("read-content")
    policy = custom / "agents/openai.yaml"
    policy.write_text("policy:\n  allow_implicit_invocation: false\n")
    # When the Claude adapter installs the site skill.
    install_client("claude", tmp_path / "profile")
    # Then the equivalent host invocation control is preserved.
    entry = tmp_path / "profile/.claude/skills/read-content/SKILL.md"
    frontmatter = yaml.safe_load(entry.read_text().split("---", 2)[1])
    assert frontmatter["disable-model-invocation"] is True
