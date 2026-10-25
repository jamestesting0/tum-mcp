"""Participation-bound workspaces; no start, hooks, installers, or submission effects."""

import hashlib
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import Field

from tum_mcp.artemis import Artemis
from tum_mcp.artemis_models import ExerciseView
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.git_ops import repository_url, run_git
from tum_mcp.moodle.config import private_write
from tum_mcp.parsing import decode
from tum_mcp.settings import Frozen, PositiveId, preferences


class WorkspaceReceipt(Frozen):
    account_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    instance_id: str
    course_id: PositiveId
    exercise_id: PositiveId
    participation_id: PositiveId
    mode: Literal["graded", "practice"]
    repository: str
    branch: str
    base_revision: str
    workspace: Path
    prepared_at: float


def prepare(
    provider: Artemis, view: ExerciseView, mode: Literal["graded", "practice"]
) -> WorkspaceReceipt:
    if not provider.api.account.workspace_writes:
        raise CampusError(
            Code.ACTION_REQUIRED, "Enable workspace preparation with the local scope command first."
        )
    participation = provider.participation(view.exercise, mode)
    if view.exercise.allow_offline_ide is not True:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Offline IDE permission is unavailable or disabled."
        )
    if not participation.repository_uri or not participation.branch:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "No verified repository/branch is exposed.")
    repository = repository_url(
        participation.repository_uri.get_secret_value(), provider.api.account
    )
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", participation.branch)
        or ".." in participation.branch
    ):
        raise CampusError(Code.SCOPE_DENIED, "Unsafe branch name.")
    root = preferences().workspace_root.expanduser().resolve()
    destination = root / f"course-{view.course_id}" / f"exercise-{view.exercise.id}-{mode}"
    if not destination.resolve().is_relative_to(root):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Workspace escapes the approved root.")
    marker = destination / ".tum-mcp-workspace.json"
    if destination.exists():
        if not marker.is_file():
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Existing folder has no matching workflow receipt."
            )
        receipt = decode(WorkspaceReceipt, marker.read_bytes())
        if (
            receipt.account_id != view.account_id
            or receipt.exercise_id != view.exercise.id
            or receipt.participation_id != participation.id
            or receipt.mode != mode
            or receipt.repository != repository
            or receipt.workspace != destination
        ):
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Workspace belongs to another participation."
            )
        if run_git(destination, ["remote", "get-url", "origin"]) != repository:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Workspace remote changed.")
        return receipt
    credentials = Vault().load(provider.api.account)
    if not any(item.url == repository for item in credentials.repositories):
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Import this repository's Git token with tum-mcp workspace connect-git first.",
        )
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_git(
        destination.parent,
        [
            "clone",
            "--no-recurse-submodules",
            "--branch",
            participation.branch,
            "--",
            repository,
            str(destination),
        ],
        provider.api.account,
    )
    receipt = WorkspaceReceipt(
        account_id=view.account_id,
        instance_id=view.instance_id,
        course_id=view.course_id,
        exercise_id=view.exercise.id,
        participation_id=participation.id,
        mode=mode,
        repository=repository,
        branch=participation.branch,
        base_revision=run_git(destination, ["rev-parse", "HEAD"]),
        workspace=destination,
        prepared_at=time.time(),
    )
    private_write(marker, receipt.model_dump_json(indent=2).encode())
    return receipt


def workflow_status(path: Path) -> WorkspaceReceipt:
    root = preferences().workspace_root.expanduser().resolve()
    if not path.resolve().is_relative_to(root):
        raise CampusError(Code.SCOPE_DENIED, "Workspace is outside the configured root.")
    marker = path / ".tum-mcp-workspace.json"
    if not marker.is_file():
        raise CampusError(Code.WORKSPACE_CONFLICT, "No workflow receipt exists here.")
    receipt = decode(WorkspaceReceipt, marker.read_bytes())
    if receipt.workspace.resolve() != path.resolve():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Workflow receipt belongs to another directory.")
    git_directory = path / ".git"
    if not git_directory.is_dir() or git_directory.is_symlink() or marker.is_symlink():
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Workspace Git metadata or receipt is not local."
        )
    if Path(run_git(path, ["rev-parse", "--show-toplevel"])).resolve() != path.resolve():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Git worktree points to another directory.")
    return receipt


def fingerprint(path: Path) -> str:
    hasher = hashlib.sha256()
    names = run_git(path, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    for name in sorted(set(names.split("\0")) - {"", ".tum-mcp-workspace.json"}):
        source = path / name
        if source.is_symlink() or not source.resolve().is_relative_to(path.resolve()):
            raise CampusError(
                Code.SCOPE_DENIED, "A tracked path is a symlink or escapes the workspace."
            )
        hasher.update(name.encode() + b"\0")
        if source.is_file():
            if source.stat().st_size > 50 * 1024 * 1024:
                raise CampusError(
                    Code.CAPABILITY_UNSUPPORTED, "Source file exceeds fingerprint budget."
                )
            with source.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    hasher.update(chunk)
        else:
            hasher.update(b"<deleted>")
    return hasher.hexdigest()
