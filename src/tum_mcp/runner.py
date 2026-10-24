"""Approved container recipes with bounded output and no home/credential mounts."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

import anyio
from filelock import FileLock

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen, Provider, TestRecipe, data_dir, find_account, preferences
from tum_mcp.workspace import fingerprint, workflow_status


class TestReceipt(Frozen):
    account_id: str
    course_id: int
    exercise_id: int
    participation_id: int
    mode: Literal["graded", "practice"]
    recipe: str
    command: tuple[str, ...]
    image: str
    workspace: Path
    fingerprint_before: str
    fingerprint_after: str
    exit_status: int
    started_at: float
    finished_at: float
    output_excerpt: str
    output_truncated: bool
    isolation: str = "docker_network_none_no_host_home"
    verification_level: Literal["targeted", "full"] = "targeted"


def docker_command(executable: str, recipe: TestRecipe, workspace: Path, name: str) -> list[str]:
    if "," in str(workspace):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Container workspace path cannot contain a comma."
        )
    identity = str(os.getuid()) if hasattr(os, "getuid") else "65534"
    return [
        executable,
        "run",
        "--rm",
        "--pull=never",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "--cpus=2",
        "--memory=1g",
        "--user",
        identity,
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=256m,mode=1777",  # noqa: S108 -- container tmpfs, not host
        "--tmpfs",
        "/home/student:rw,nosuid,nodev,size=64m,mode=1777",
        "--env",
        "HOME=/home/student",
        "--workdir",
        "/workspace",
        "--mount",
        f"type=bind,source={workspace},target=/workspace",
        "--mount",
        f"type=bind,source={workspace / '.git'},target=/workspace/.git,readonly",
        recipe.image,
        *recipe.argv,
    ]


async def execute(command: list[str], recipe: TestRecipe) -> tuple[int, bytes, bool]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "DOCKER_HOST", "DOCKER_CONTEXT"}
    }
    captured = bytearray()
    truncated = False
    try:
        with anyio.fail_after(recipe.timeout_seconds):
            async with await anyio.open_process(
                command,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            ) as process:
                if process.stdout is None:
                    raise CampusError(
                        Code.CAPABILITY_UNSUPPORTED, "Test output stream is unavailable."
                    )
                async for chunk in process.stdout:
                    if len(captured) + len(chunk) > 64000:
                        truncated = True
                        process.terminate()
                        break
                    captured.extend(chunk)
                return await process.wait(), bytes(captured), truncated
    except TimeoutError:
        raise CampusError(
            Code.PENDING, "Test recipe timed out; inspect the workspace before retrying."
        ) from None
    except OSError:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Container engine is unavailable.") from None
    finally:
        # Kill only this unique container, including when the client timed out/cancelled.
        with anyio.CancelScope(shield=True), anyio.move_on_after(10):
            await anyio.run_process(
                [command[0], "rm", "--force", command[command.index("--name") + 1]],
                env=environment,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def run_tests(workspace: Path, recipe_name: str) -> TestReceipt:
    receipt = workflow_status(workspace)
    account = find_account(receipt.account_id, Provider.ARTEMIS)
    if receipt.course_id not in account.courses:
        raise CampusError(Code.SCOPE_DENIED, "This course is no longer locally enabled.")
    recipes = [
        recipe
        for recipe in preferences().test_recipes
        if recipe.name == recipe_name
        and recipe.account_id == receipt.account_id
        and recipe.course_id == receipt.course_id
    ]
    if len(recipes) != 1:
        raise CampusError(
            Code.ACTION_REQUIRED, "Configure one approved, course-bound test recipe locally."
        )
    executable = shutil.which("docker")
    if not executable:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "A running Docker engine is required for isolated tests."
        )
    recipe = recipes[0]
    directory = data_dir() / "workflow-state"
    directory.mkdir(mode=0o700, exist_ok=True)
    with FileLock(str(directory / f"{receipt.account_id}-{receipt.exercise_id}.lock")):
        before = fingerprint(workspace)
        started = time.time()
        result, output, truncated = anyio.run(
            execute,
            docker_command(executable, recipe, workspace.resolve(), "tum-mcp-" + uuid4().hex),
            recipe,
        )
        record = TestReceipt(
            account_id=receipt.account_id,
            course_id=receipt.course_id,
            exercise_id=receipt.exercise_id,
            participation_id=receipt.participation_id,
            mode=receipt.mode,
            recipe=recipe.name,
            command=recipe.argv,
            image=recipe.image,
            workspace=workspace.resolve(),
            fingerprint_before=before,
            fingerprint_after=fingerprint(workspace),
            exit_status=result,
            started_at=started,
            finished_at=time.time(),
            output_excerpt=output.decode(errors="replace")[-8000:],
            output_truncated=truncated,
            verification_level=recipe.verification_level,
        )
        from tum_mcp.test_receipts import save_test_receipt

        save_test_receipt(receipt, record)
        return record
