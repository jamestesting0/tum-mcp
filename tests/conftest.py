from pathlib import Path

import pytest
from keyring.backend import KeyringBackend

from tum_mcp.moodle import auth


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.values[service, username]


@pytest.fixture
def memory_keyring(monkeypatch: pytest.MonkeyPatch) -> KeyringBackend:
    backend = MemoryKeyring()
    monkeypatch.setattr(auth, "system_keyring", lambda: backend)
    return backend


@pytest.fixture
def lecture_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Opt in explicitly for lecture scenarios; ordinary fixtures keep the base surface."""
    from tum_mcp.extensions import LectureInstallation

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "lecture-data"))
    folder = tmp_path / "lecture-data/config"
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(folder))
    folder.mkdir(parents=True)
    selected = LectureInstallation(
        enabled=True,
        installed_at="2026-10-26T10:00:00Z",
        package_version="fixture",
        asr_requested=False,
    )
    (folder / "lecture-extension.json").write_text(selected.model_dump_json())
    return folder


@pytest.fixture
def course_memory(lecture_extension: Path) -> Path:
    """Enable memory explicitly for graph fixtures, including their synthetic lecture."""
    (lecture_extension / "extensions.json").write_text('{"schema_version":1,"course_memory":true}')
    return lecture_extension
