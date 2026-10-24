import io
import sys
from pathlib import Path

import pytest
from keyring.backend import KeyringBackend
from pydantic import SecretStr

from tum_mcp import git_helper
from tum_mcp.credentials import Credential, RepositorySecret, Vault
from tum_mcp.settings import Account, Provider, save_account


def test_reconnect_keeps_scopes_and_repository_secrets_but_rotates_grants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_keyring: KeyringBackend,
) -> None:
    from tum_mcp.connect import existing_account
    from tum_mcp.settings import find_account

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    account = Account(
        provider=Provider.ARTEMIS,
        origin="https://artemis.tum.de",
        principal="7",
        courses=(77,),
        sensitive_reads=True,
        workspace_writes=True,
    )
    save_account(account)
    secret = RepositorySecret(
        url=account.origin + "/git/course/student.git",
        username=SecretStr("student"),
        password=SecretStr("synthetic-token"),
    )
    vault = Vault()
    vault.save(account, Credential(account_id=account.id, repositories=(secret,)))
    generation = vault.load(account).generation
    reconnected = existing_account(
        Account(
            provider=Provider.ARTEMIS,
            origin=account.origin,
            principal="7",
        )
    )
    vault.replace_login(reconnected, Credential(account_id=account.id))
    save_account(reconnected)
    current = find_account(account.id, Provider.ARTEMIS)
    assert current.courses == (77,)
    assert current.sensitive_reads and current.workspace_writes
    assert current.scope_revision == 2
    assert vault.load(current).repositories == (secret,)
    assert vault.load(current).generation != generation


@pytest.mark.parametrize(
    "path,allowed", [("git/course/student.git", True), ("git/other/student.git", False)]
)
def test_git_helper_releases_token_only_to_the_exact_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_keyring: KeyringBackend,
    capsys: pytest.CaptureFixture[str],
    path: str,
    allowed: bool,
) -> None:
    # Given one encrypted, repository-scoped token and no inherited host credentials.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    account = Account(provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7")
    save_account(account)
    repository = RepositorySecret(
        url=account.origin + "/git/course/student.git",
        username=SecretStr("student"),
        password=SecretStr("synthetic-repository-token"),
    )
    saved = Credential(account_id=account.id, repositories=(repository,))
    vault = Vault()
    vault.save(account, saved)
    monkeypatch.setenv("TUM_MCP_GIT_ACCOUNT", account.id)
    monkeypatch.setattr(sys, "argv", ["git_helper", "get"])
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(f"protocol=https\nhost=artemis.tum.de\npath={path}\n\n")
    )
    # When Git asks for that exact path or an unrelated repository.
    git_helper.main()
    # Then credentials are available only on the authorized Git pipe, never in normal serialization.
    output = capsys.readouterr().out
    assert ("password=synthetic-repository-token" in output) is allowed
    assert "synthetic-repository-token" not in saved.model_dump_json()
    assert "synthetic-repository-token" not in repr(saved)
    assert (
        b"synthetic-repository-token"
        not in next((tmp_path / "credentials").glob("*.enc")).read_bytes()
    )
