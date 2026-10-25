import io
import json
from pathlib import Path

import pytest
import yaml

from tum_mcp.clients import install_client
from tum_mcp.errors import CampusError
from tum_mcp.skills import customize_skill, export_pack, skill_diff
from tum_mcp.uninstall import uninstall_client


def test_skills_and_client_configuration_use_utf8_with_a_legacy_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.skill_validation import validate_skills

    # Given UTF-8 skills and user settings on a Windows-style default code page.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "client profile"
    home.mkdir()
    config = home / ".claude.json"
    original = {"displayName": "München 漢字", "mcpServers": {"other": {"command": "keep"}}}
    config.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(io, "text_encoding", lambda encoding, stacklevel=2: encoding or "cp1252")

    # When the pack is validated and the client registration is installed and removed.
    report = validate_skills()
    install_client("claude", home)
    uninstall_client("claude", home)

    # Then every skill remains readable and unrelated Unicode settings survive.
    assert len(report.checked_skills) == 4
    assert report.errors == ()
    assert json.loads(config.read_text(encoding="utf-8")) == original


def test_claude_install_preserves_other_settings_and_customized_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an isolated client profile with unrelated user settings.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "client profile"
    home.mkdir()
    config = home / ".claude.json"
    config.write_text(
        json.dumps({"customSetting": 42, "mcpServers": {"other": {"command": "keep"}}})
    )
    # When setup runs twice using the same package.
    install_client("claude", home)
    install_client("claude", home)
    # Then unrelated settings survive and the site skill stays discoverable.
    parsed = json.loads(config.read_text(encoding="utf-8"))
    assert parsed["customSetting"] == 42
    assert parsed["mcpServers"]["other"] == {"command": "keep"}
    assert parsed["mcpServers"]["tum"]["args"] == ["-I", "-m", "tum_mcp", "serve"]
    submission = home / ".claude/skills/read-content/SKILL.md"
    metadata = yaml.safe_load(submission.read_text(encoding="utf-8").split("---", 2)[1])
    assert metadata.get("disable-model-invocation") is not True
    submission.write_text(
        submission.read_text(encoding="utf-8") + "\nPersonal customization.\n", encoding="utf-8"
    )
    with pytest.raises(CampusError, match="WORKSPACE_CONFLICT"):
        install_client("claude", home)
    assert submission.read_text(encoding="utf-8").endswith("Personal customization.\n")


def test_personal_skill_override_survives_package_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a user-owned customization outside package directories.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    custom = customize_skill("read-content")
    source = custom / "SKILL.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nPrefer German summaries.\n", encoding="utf-8"
    )
    assert "+Prefer German summaries." in skill_diff("read-content")
    # When the Codex adapter exports its installed pack.
    home = tmp_path / "profile"
    install_client("codex", home)
    # Then it installs that single customized copy and keeps the original user override intact.
    installed = home / ".codex/plugins/local/tum-mcp/skills/read-content/SKILL.md"
    assert installed.read_bytes() == source.read_bytes()
    assert len(list((home / ".codex/plugins/local/tum-mcp/skills").glob("read-content"))) == 1
    root = home / ".codex/plugins/local/tum-mcp"
    manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert len(manifest["extensions"]["com.openai"]["interface"]["shortDescription"]) <= 30
    mcp = json.loads((root / "mcp.json").read_text(encoding="utf-8"))
    assert mcp["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    assert mcp["mcpServers"]["tum"]["command"] == "node"
    assert mcp["mcpServers"]["tum"]["args"] == ["${PLUGIN_ROOT}/scripts/serve.mjs"]
    assert "['-I', '-m', 'tum_mcp', 'serve']" in (root / "scripts/serve.mjs").read_text(
        encoding="utf-8"
    )


def test_skill_export_rejects_symlinked_private_files_before_creating_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    custom = customize_skill("read-content")
    private = tmp_path / "private.txt"
    private.write_text("synthetic-private-canary")
    try:
        (custom / "unexpected.txt").symlink_to(private)
    except OSError:
        pytest.skip("This platform/profile cannot create symlinks.")
    destination = tmp_path / "export"
    with pytest.raises(CampusError, match="symbolic links"):
        export_pack(destination)
    assert not destination.exists()
