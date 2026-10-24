"""Canonical action identities and minimal receipts, separate from permission text."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, RootModel

from tum_mcp.settings import Frozen, PositiveId


class ActionTarget(Frozen):
    account_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    instance_id: str
    principal: str
    credential_generation: str
    course_id: PositiveId
    exercise_id: PositiveId
    mode: Literal["graded", "practice"]
    constraint_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class StartAction(ActionTarget):
    kind: Literal["start"] = "start"


class SubmitAction(ActionTarget):
    kind: Literal["submit"] = "submit"
    participation_id: PositiveId
    repository: str
    branch: str
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    workspace: Path
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    test_receipt_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


Action = Annotated[StartAction | SubmitAction, Field(discriminator="kind")]


class ActionEnvelope(RootModel[Action]):
    pass


def action_fingerprint(action: Action) -> str:
    return hashlib.sha256(
        json.dumps(action.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ActionReview(Frozen):
    action: Action
    fingerprint: str
    title: str
    deadline: str
    submission_policy: str
    team_action: bool
    limitations: tuple[str, ...]
    changed_files: tuple[str, ...] = ()


class Grant(Frozen):
    fingerprint: str
    account_id: str
    principal: str
    expires_at: float
    attempts: Literal[1] = 1
    nonce: str


class ActionReceipt(Frozen):
    action: Action
    fingerprint: str
    account_id: str
    course_id: int
    exercise_id: int
    mode: Literal["graded", "practice"]
    kind: Literal["start", "submit"]
    status: Literal["reserved", "in_flight", "confirmed", "unknown", "denied"]
    attempt_id: str
    attempted_at: float
    approval_expires_at: float
    finished_at: float | None = None
    participation_id: int | None = None
    commit: str | None = None
    message: str
