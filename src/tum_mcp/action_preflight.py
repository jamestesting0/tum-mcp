"""Fresh, exercise-specific reviews before any remote-action grant can be used."""

import hashlib
import json
import time
from pathlib import Path
from typing import Literal

from tum_mcp.action_models import (
    ActionReview,
    ActionTarget,
    StartAction,
    SubmitAction,
    action_fingerprint,
)
from tum_mcp.artemis import Artemis
from tum_mcp.artemis_models import ExerciseView
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.git_ops import repository_url
from tum_mcp.settings import Frozen, preferences
from tum_mcp.submission import preview
from tum_mcp.test_receipts import load_test_receipt


class Constraints(Frozen):
    release: str | None
    deadline: str | None
    mode: str | None
    participation_id: int | None
    submission_count: int | None
    policy: str
    sensitive_reads: bool
    workspace_writes: bool
    remote_actions: bool
    scope_revision: int
    statement_fingerprint: str
    assistance_mode: str
    offline_ide: bool | None


class Preflight:
    def __init__(self, provider: Artemis) -> None:
        self.provider = provider

    def target(self, view: ExerciseView, mode: Literal["graded", "practice"]) -> ActionTarget:
        account = self.provider.api.account
        if not account.remote_actions or not account.sensitive_reads:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Remote actions and own-participation reads require separate local enablement.",
            )
        participations = view.exercise.student_participations or ()
        chosen = next((p for p in participations if p.test_run == (mode == "practice")), None)
        graded = next((p for p in participations if not p.test_run), None)
        deadline_owner = chosen or graded
        deadline = (
            deadline_owner.individual_due_date if deadline_owner else None
        ) or view.exercise.due_date
        if mode == "graded" and deadline is not None and deadline.timestamp() <= time.time():
            raise CampusError(
                Code.SCOPE_DENIED,
                "Graded deadline passed; use the manual course path for late actions.",
            )
        if mode == "practice" and (deadline is None or deadline.timestamp() > time.time()):
            raise CampusError(
                Code.SCOPE_DENIED,
                "Practice participation requires a known elapsed effective deadline.",
            )
        policy = view.exercise.submission_policy
        if (
            policy
            and policy.active
            and (
                policy.type not in {"lock_repository", "submission_penalty"}
                or policy.submission_limit is None
                or (chosen is not None and chosen.submission_count is None)
                or (policy.type == "submission_penalty" and policy.exceeding_penalty is None)
            )
        ):
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "Active submission restrictions are incomplete."
            )
        if (
            policy
            and policy.active
            and policy.type == "lock_repository"
            and chosen
            and policy.submission_limit is not None
            and chosen.submission_count is not None
            and chosen.submission_count >= policy.submission_limit
        ):
            raise CampusError(Code.SCOPE_DENIED, "The repository submission limit is exhausted.")
        constraints = Constraints(
            release=view.exercise.release_date.isoformat() if view.exercise.release_date else None,
            deadline=deadline.isoformat() if deadline else None,
            mode=view.exercise.mode,
            participation_id=chosen.id if chosen else None,
            submission_count=chosen.submission_count if chosen else None,
            policy=policy.model_dump_json() if policy else "not_exposed",
            sensitive_reads=account.sensitive_reads,
            workspace_writes=account.workspace_writes,
            remote_actions=account.remote_actions,
            scope_revision=account.scope_revision,
            statement_fingerprint=hashlib.sha256(
                (view.exercise.problem_statement or "").encode()
            ).hexdigest(),
            assistance_mode=preferences().assistance_mode,
            offline_ide=view.exercise.allow_offline_ide,
        )
        return ActionTarget(
            account_id=account.id,
            instance_id=account.origin,
            principal=account.principal,
            credential_generation=Vault().load(account).generation,
            course_id=view.course_id,
            exercise_id=view.exercise.id,
            mode=mode,
            constraint_fingerprint=hashlib.sha256(
                constraints.model_dump_json().encode()
            ).hexdigest(),
        )

    def review(self, action: StartAction | SubmitAction, view: ExerciseView) -> ActionReview:
        policy = view.exercise.submission_policy
        owner = next(
            (
                p
                for p in view.exercise.student_participations or ()
                if p.test_run == (action.mode == "practice")
            ),
            None,
        )
        graded = next(
            (p for p in view.exercise.student_participations or () if not p.test_run), None
        )
        deadline_owner = owner or graded
        deadline = (
            deadline_owner.individual_due_date if deadline_owner else None
        ) or view.exercise.due_date
        return ActionReview(
            action=action,
            fingerprint=action_fingerprint(action),
            title=view.exercise.title,
            deadline=deadline.isoformat() if deadline else "not_exposed",
            submission_policy=policy.model_dump_json() if policy else "not_exposed",
            team_action=view.exercise.mode != "INDIVIDUAL",
            limitations=(
                "Confirm the course permits your assistance mode before approving.",
                "One approval permits one exact attempt; uncertain outcomes are never retried.",
                "Native host Git/SSH access remains outside this broker's enforcement boundary.",
            ),
        )

    def start(
        self, course_id: int, exercise_id: int, mode: Literal["graded", "practice"]
    ) -> ActionReview:
        view = self.provider.exercise(course_id, exercise_id)
        target = self.target(view, mode)
        if any(
            p.test_run == (mode == "practice") for p in view.exercise.student_participations or ()
        ):
            raise CampusError(
                Code.ACTION_REQUIRED,
                "This participation already exists; reuse it without another start request.",
            )
        action = StartAction(**target.model_dump())
        return self.review(action, view)

    def submit(self, workspace: Path) -> ActionReview:
        snapshot = preview(workspace)
        if snapshot.working_tree_changes:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Commit the reviewed changes explicitly before submission."
            )
        if not snapshot.local_tests_match:
            raise CampusError(
                Code.STALE_RESULT,
                "A passing isolated test receipt must match the exact workspace content.",
            )
        receipt = snapshot.workflow
        view = self.provider.exercise(receipt.course_id, receipt.exercise_id)
        participation = self.provider.participation(view.exercise, receipt.mode)
        if participation.id != receipt.participation_id or not participation.repository_uri:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Participation/repository changed since preparation."
            )
        expected = repository_url(
            participation.repository_uri.get_secret_value(), self.provider.api.account
        )
        if expected != receipt.repository or participation.branch != receipt.branch:
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Submission destination differs from the live participation.",
            )
        target = self.target(view, receipt.mode)
        tests = load_test_receipt(receipt)
        action = SubmitAction(
            **target.model_dump(),
            participation_id=participation.id,
            repository=expected,
            branch=receipt.branch,
            commit=snapshot.commit,
            workspace=workspace.resolve(),
            source_fingerprint=tests.fingerprint_after,
            test_receipt_fingerprint=hashlib.sha256(
                json.dumps(tests.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest(),
        )
        return self.review(action, view).model_copy(
            update={"changed_files": snapshot.changed_files}
        )
