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
