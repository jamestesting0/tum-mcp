import os
import shutil
import subprocess
from pathlib import Path

import pytest
from keyring.backend import KeyringBackend

from tum_mcp.runner import run_tests
from tum_mcp.settings import Account, Preferences, Provider, config_dir
from tum_mcp.settings import TestRecipe as Recipe
from tum_mcp.workspace import WorkspaceReceipt


def test_real_container_blocks_host_secrets_network_and_git_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_keyring: KeyringBackend,
) -> None:
    image = os.environ.get("TUM_MCP_DOCKER_IMAGE")
    if not image:
        pytest.skip("Set TUM_MCP_DOCKER_IMAGE to a reviewed, already-present image digest with sh.")
    # Given a synthetic course/workspace and a secret that must stay on the host.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_HOST_CANARY", "synthetic-secret-do-not-forward")
    account = Account(
        provider=Provider.ARTEMIS,
        origin="https://artemis.tum.de",
        principal="fixture",
        courses=(77,),
    )
    root = tmp_path / "workspaces"
    directory = root / "assignment"
    directory.mkdir(parents=True)
    executable = shutil.which("git")
    assert executable is not None
    for args in (["init", "--quiet"],):
        subprocess.run([executable, "-C", str(directory), *args], check=True, capture_output=True)  # noqa: S603
    (directory / "source.txt").write_text("fixture source\n")
    subprocess.run([executable, "-C", str(directory), "add", "source.txt"], check=True)  # noqa: S603
    receipt = WorkspaceReceipt(
        account_id=account.id,
        instance_id=account.origin,
        course_id=77,
        exercise_id=11,
        participation_id=9,
        mode="graded",
        repository=account.origin + "/git/course/student.git",
        branch="main",
        base_revision="a" * 40,
        workspace=directory,
        prepared_at=0,
    )
    (directory / ".tum-mcp-workspace.json").write_text(receipt.model_dump_json())
    script = (
        'set -eu; test -z "${TUM_MCP_HOST_CANARY:-}"; test -z "${SSH_AUTH_SOCK:-}"; '
        "test ! -e /var/run/docker.sock; test ! -e /Users; "
        'test "$(wc -l < /proc/net/route)" -eq 1; '
        "if printf malicious >> /workspace/.git/config; then exit 61; fi; "
        "printf ISOLATION_OK"
    )
    recipe = Recipe(
        name="isolation-check",
        account_id=account.id,
        course_id=77,
        image=image,
        argv=("sh", "-c", script),
        timeout_seconds=30,
    )
    settings = Preferences(accounts=(account,), workspace_root=root, test_recipes=(recipe,))
    (config_dir() / "preferences.json").write_text(settings.model_dump_json())
    # When the real container executes a hostile test recipe.
    result = run_tests(directory, recipe.name)
    # Then it cannot reach host secrets/network or alter host Git execution settings.
    assert result.exit_status == 0, result.output_excerpt
    assert "ISOLATION_OK" in result.output_excerpt
    assert "synthetic-secret-do-not-forward" not in result.output_excerpt
    assert result.fingerprint_before == result.fingerprint_after
    assert "malicious" not in (directory / ".git/config").read_text()
