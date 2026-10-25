from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest
from keyring.backend import KeyringBackend

from tum_mcp import actions, remote_gate, submission
from tum_mcp.action_models import ActionReview
from tum_mcp.action_preflight import Preflight
from tum_mcp.approvals import Approvals
from tum_mcp.artemis import Artemis
from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.git_ops import run_git
from tum_mcp.runner import TestReceipt as Receipt
from tum_mcp.settings import (
    Account,
    Provider,
    config_dir,
    find_account,
    preferences,
    save_account,
)
from tum_mcp.settings import TestRecipe as Recipe
from tum_mcp.test_receipts import save_test_receipt
from tum_mcp.transport import API
from tum_mcp.workspace import WorkspaceReceipt, fingerprint


@pytest.fixture
def campus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_keyring: KeyringBackend,
) -> tuple[Callable[[], Preflight], list[str], dict[str, bool]]:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    account = Account(
        provider=Provider.ARTEMIS,
        origin="https://artemis.tum.de",
        principal="7",
        courses=(77,),
        sensitive_reads=True,
        workspace_writes=True,
        remote_actions=True,
    )
    save_account(account)
    Vault().save(account, Credential(account_id=account.id))
    visited: list[str] = []
    state = {"started": False, "lose_response": False}

    def handler(request: httpx2.Request) -> httpx2.Response:
        visited.append(request.method + " " + request.url.path)
        exercise = {
            "id": 11,
            "title": "Synthetic assignment",
            "type": "programming",
            "course": {"id": 77},
            "releaseDate": "2020-01-01T00:00:00Z",
            "dueDate": "2099-01-01T00:00:00Z",
            "mode": "INDIVIDUAL",
            "studentParticipations": [
                {
                    "id": 9,
                    "testRun": False,
                    "branch": "main",
                    "submissionCount": 0,
                    "repositoryUri": "https://artemis.tum.de/git/course/student.git",
                }
            ]
            if state["started"]
            else [],
        }
        if request.method == "POST":
            assert request.url.path == "/api/exercise/exercises/11/participations"
            state["started"] = True
            if state["lose_response"]:
                raise httpx2.ReadError("synthetic lost response")
            return httpx2.Response(201, json={"id": 9, "testRun": False})
        routes = {
            "/api/core/public/account": {"id": 7, "login": "synthetic"},
            "/api/course/courses/77/exercises-for-overview": {"exercises": [exercise]},
            "/api/exercise/exercises/11/details": {"exercise": exercise},
        }
        return httpx2.Response(200, json=routes[request.url.path])

    def api(account: Account, credential: Credential | None = None) -> API:
        return API(account, credential, httpx2.MockTransport(handler))

    monkeypatch.setattr(actions, "API", api)
    monkeypatch.setattr(submission, "API", api)

    def preflight() -> Preflight:
        return Preflight(Artemis(api(find_account(account.id, Provider.ARTEMIS))))

    return preflight, visited, state


@pytest.fixture
def tested_workspace(campus, tmp_path: Path) -> Path:
    preflight, _, state = campus
    state["started"] = True
    account = preflight().provider.api.account
    directory = tmp_path / "assignments" / "exercise"
    directory.mkdir(parents=True)
    run_git(directory, ["init", "--initial-branch=main"])
    (directory / "main.py").write_text("print('fixture')\n", encoding="utf-8")
    run_git(directory, ["add", "main.py"])
    run_git(
        directory,
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "Synthetic initial revision",
        ],
    )
    repository = "https://artemis.tum.de/git/course/student.git"
    run_git(directory, ["remote", "add", "origin", repository])
    workflow = WorkspaceReceipt(
        account_id=account.id,
        instance_id=account.origin,
        course_id=77,
        exercise_id=11,
        participation_id=9,
        mode="graded",
        repository=repository,
        branch="main",
        base_revision=run_git(directory, ["rev-parse", "HEAD"]),
        workspace=directory,
        prepared_at=0,
    )
    (directory / ".tum-mcp-workspace.json").write_text(workflow.model_dump_json(), encoding="utf-8")
    recipe = Recipe(
        name="full-suite",
        account_id=account.id,
        course_id=77,
        image="fixture@sha256:" + "c" * 64,
        argv=("pytest",),
        verification_level="full",
    )
    config = preferences().model_copy(
        update={
            "workspace_root": directory.parent,
            "test_recipes": (recipe,),
        }
    )
    (config_dir() / "preferences.json").write_text(config.model_dump_json(), encoding="utf-8")
    content = fingerprint(directory)
    evidence = Receipt(
        account_id=account.id,
        course_id=77,
        exercise_id=11,
        participation_id=9,
        mode="graded",
        recipe=recipe.name,
        image=recipe.image,
        command=recipe.argv,
        verification_level="full",
        workspace=directory,
        fingerprint_before=content,
        fingerprint_after=content,
        exit_status=0,
        started_at=0,
        finished_at=1,
        output_excerpt="synthetic tests passed",
        output_truncated=False,
    )
    save_test_receipt(workflow, evidence)
    return directory


def approve(review: ActionReview) -> None:
    Approvals(Vault()).issue(review.action)


def test_release_gate_blocks_remote_actions_even_with_a_valid_grant(campus) -> None:
    preflight, visited, _ = campus
    review = preflight().start(77, 11, "graded")
    approve(review)
    visited.clear()
    with pytest.raises(CampusError, match="unavailable"):
        actions.execute(review)
    assert visited == []


@pytest.mark.parametrize("legacy_flag", [False, True])
def test_a_legacy_verified_flag_and_valid_grant_cannot_enable_remote_actions(
    campus, monkeypatch: pytest.MonkeyPatch, legacy_flag: bool
) -> None:
    # Given retained approval data and any value of the retired release flag.
    monkeypatch.setattr(remote_gate, "REMOTE_ACTIONS_VERIFIED", legacy_flag)
    preflight, visited, _ = campus
    review = preflight().start(77, 11, "graded")
    approve(review)
    visited.clear()
    # When an old caller attempts execution, it is denied before campus access.
    with pytest.raises(CampusError) as error:
        actions.execute(review)
    assert error.value.code == Code.CAPABILITY_UNSUPPORTED
    assert visited == []


def test_dirty_content_and_changed_recipe_invalidate_passing_tests(
    campus,
    tested_workspace: Path,
) -> None:
    preflight, _, _ = campus
    assert preflight().submit(tested_workspace).action.kind == "submit"
    (tested_workspace / "main.py").write_text("print('changed')\n", encoding="utf-8")
    with pytest.raises(CampusError, match="Commit the reviewed changes"):
        preflight().submit(tested_workspace)
    run_git(tested_workspace, ["restore", "main.py"])
    config = preferences()
    recipe = config.test_recipes[0].model_copy(update={"verification_level": "targeted"})
    (config_dir() / "preferences.json").write_text(
        config.model_copy(update={"test_recipes": (recipe,)}).model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(CampusError, match="passing isolated test receipt"):
        preflight().submit(tested_workspace)


def test_git_url_rewrites_are_rejected_before_credential_access(
    campus,
    tested_workspace: Path,
) -> None:
    preflight, _, _ = campus
    account = preflight().provider.api.account
    run_git(
        tested_workspace,
        [
            "config",
            "url.https://external.invalid/.insteadOf",
            "https://artemis.tum.de/",
        ],
    )
    with pytest.raises(CampusError, match="Unexpected local Git configuration"):
        run_git(tested_workspace, ["ls-remote", "origin"], account)
