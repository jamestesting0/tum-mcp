from pathlib import Path

import pytest
from filelock import FileLock

from tum_mcp.connect import ServiceChoice, available_services
from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import install_lecture, lecture_enabled, require_lecture, uninstall_lecture
from tum_mcp.lecture_processing import runtime
from tum_mcp.skill_catalog import CURRENT_SKILLS
from tum_mcp.skills import inspect_skills


@pytest.fixture
def isolated_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(data))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(data / "config"))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return data


def test_base_keeps_existing_skills_and_services_until_explicit_install(
    isolated_extension: Path,
) -> None:
    assert {skill["name"] for skill in inspect_skills()} == set(CURRENT_SKILLS)
    assert ServiceChoice.TUM_LIVE not in available_services()
    with pytest.raises(CampusError, match="install lecture"):
        require_lecture()
    assert not isolated_extension.exists()


def test_install_and_repeat_preserve_selection_without_fetching_models(
    isolated_extension: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runtime, "install", lambda: pytest.fail("--no-asr cannot install an engine")
    )
    first = install_lecture(asr=False)
    record = isolated_extension / "config/lecture-extension.json"
    selected = record.read_bytes()
    second = install_lecture(asr=False)
    assert lecture_enabled() and first["enabled"] and second["enabled"]
    assert record.read_bytes() == selected
    assert {skill["name"] for skill in inspect_skills()} == {*CURRENT_SKILLS, "prepare-lecture"}
    assert ServiceChoice.TUM_LIVE in available_services()
    assert not (isolated_extension / "lecture-runtime").exists()


def test_unsupported_asr_host_still_installs_caption_and_notes_workflow(
    isolated_extension: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "supported", lambda: False)
    monkeypatch.setattr(
        runtime, "install", lambda: pytest.fail("Unsupported hosts cannot install MLX")
    )
    result = install_lecture()
    assert result["enabled"] and not result["recognition"]["supported"]
    assert "prepare-lecture" in {item["name"] for item in inspect_skills()}


def test_failed_recognizer_install_keeps_the_previous_base_setup(
    isolated_extension: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import extensions

    def failed(_requested: bool):
        raise CampusError(Code.OFFLINE, "Synthetic dependency failure")

    monkeypatch.setattr(extensions, "prepare_recognizer", failed)
    with pytest.raises(CampusError, match="Synthetic dependency failure"):
        install_lecture()
    assert not lecture_enabled()
    assert not (isolated_extension / "config/lecture-extension.json").exists()
    assert {item["name"] for item in inspect_skills()} == set(CURRENT_SKILLS)


def test_corrupt_installation_record_is_preserved_and_base_remains_usable(
    isolated_extension: Path,
) -> None:
    record = isolated_extension / "config/lecture-extension.json"
    record.parent.mkdir(parents=True)
    record.write_text("edited by user")
    assert not lecture_enabled()
    with pytest.raises(CampusError, match="local review"):
        install_lecture(asr=False)
    assert record.read_text() == "edited by user"


def test_concurrent_extension_install_is_bounded(isolated_extension: Path) -> None:
    folder = isolated_extension / "config"
    folder.mkdir(parents=True)
    with FileLock(str(folder / "lecture-extension.lock")):
        with pytest.raises(CampusError, match="Another process"):
            install_lecture(asr=False)
    assert not lecture_enabled()


def test_removal_preserves_notes_evidence_and_saved_sessions(isolated_extension: Path) -> None:
    install_lecture(asr=False)
    keep = isolated_extension / "personal-notes.json"
    keep.write_text("User-owned notes and private evidence")
    result = uninstall_lecture()
    assert not result["enabled"] and not lecture_enabled()
    assert keep.read_text() == "User-owned notes and private evidence"
    assert {item["name"] for item in inspect_skills()} == set(CURRENT_SKILLS)
