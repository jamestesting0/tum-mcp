"""Encrypted one-use grants. This store is never exposed as an approval MCP tool."""

import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import InvalidToken
from filelock import FileLock

from tum_mcp.action_models import Action, ActionReceipt, Grant, action_fingerprint
from tum_mcp.credentials import Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.parsing import decode
from tum_mcp.settings import data_dir


class Approvals:
    def __init__(
        self, vault: Vault, root: Path | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self.vault = vault
        self.root = root or data_dir() / "actions"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.clock = clock

    def issue(self, action: Action) -> None:
        """Called only after the trusted local terminal has reviewed this exact action."""
        identity = action_fingerprint(action)
        with FileLock(str(self.root / f"{identity}.lock")):
            if (self.root / f"{identity}.receipt.enc").exists():
                raise CampusError(
                    Code.PENDING,
                    "An attempt already exists; reconcile its remote state before any new action.",
                )
            grant = Grant(
                fingerprint=identity,
                account_id=action.account_id,
                principal=action.principal,
                expires_at=self.clock() + 180,
                nonce=uuid4().hex,
            )
            private_write(
                self.root / f"{identity}.grant.enc",
                self.vault.cipher(create=True).encrypt(grant.model_dump_json().encode()),
            )

    def consume(self, action: Action) -> ActionReceipt:
        """Persist the attempt before network I/O; ambiguous failures cannot reuse it."""
        identity = action_fingerprint(action)
        with FileLock(str(self.root / f"{identity}.lock")):
            if (self.root / f"{identity}.receipt.enc").exists():
                raise CampusError(
                    Code.PENDING,
                    "This exact action already has a remote attempt; no retry was made.",
                )
            path = self.root / f"{identity}.grant.enc"
            if not path.is_file():
                raise CampusError(
                    Code.ACTION_REQUIRED,
                    "Review and approve this exact action in your own terminal.",
                )
            try:
                grant = decode(Grant, self.vault.cipher().decrypt(path.read_bytes()))
            except InvalidToken:
                raise CampusError(Code.SCOPE_DENIED, "Approval integrity check failed.") from None
            if (
                grant.fingerprint != identity
                or grant.account_id != action.account_id
                or grant.principal != action.principal
                or grant.expires_at <= self.clock()
            ):
                raise CampusError(
                    Code.SCOPE_DENIED, "Approval identity, target, or expiry does not match."
                )
            receipt = ActionReceipt(
                action=action,
                fingerprint=identity,
                account_id=action.account_id,
                course_id=action.course_id,
                exercise_id=action.exercise_id,
                mode=action.mode,
                kind=action.kind,
                status="reserved",
                attempt_id=uuid4().hex,
                attempted_at=self.clock(),
                approval_expires_at=grant.expires_at,
                message=("One approved attempt reserved; a lost response does not permit a retry."),
            )
            private_write(
                self.root / f"{identity}.receipt.enc",
                self.vault.cipher().encrypt(receipt.model_dump_json().encode()),
            )
            path.unlink()
            return receipt

    def finish(self, receipt: ActionReceipt) -> ActionReceipt:
        with FileLock(str(self.root / f"{receipt.fingerprint}.lock")):
            path = self.root / f"{receipt.fingerprint}.receipt.enc"
            previous = self.read(receipt.fingerprint)
            if (
                previous.attempt_id != receipt.attempt_id
                or previous.status != "in_flight"
                or receipt.status not in {"confirmed", "unknown", "denied"}
            ):
                raise CampusError(
                    Code.SCOPE_DENIED, "Attempt receipt changed; no overwrite was made."
                )
            completed = receipt.model_copy(update={"finished_at": self.clock()})
            private_write(path, self.vault.cipher().encrypt(completed.model_dump_json().encode()))
            return completed

    def dispatch(self, action: Action, receipt: ActionReceipt) -> None:
        identity = action_fingerprint(action)
        with FileLock(str(self.root / f"{identity}.lock")):
            previous = self.read(identity)
            if (
                previous.fingerprint != receipt.fingerprint
                or previous.action != action
                or previous.attempt_id != receipt.attempt_id
                or previous.status != "reserved"
                or previous.approval_expires_at <= self.clock()
            ):
                raise CampusError(
                    Code.SCOPE_DENIED, "Attempt was already dispatched, expired, or changed."
                )
            current = previous.model_copy(update={"status": "in_flight"})
            private_write(
                self.root / f"{identity}.receipt.enc",
                self.vault.cipher().encrypt(current.model_dump_json().encode()),
            )

    def read(self, identity: str) -> ActionReceipt:
        if len(identity) != 64 or any(
            character not in "0123456789abcdef" for character in identity
        ):
            raise CampusError(Code.SCOPE_DENIED, "Invalid action fingerprint.")
        path = self.root / f"{identity}.receipt.enc"
        if not path.is_file():
            raise CampusError(
                Code.ACTION_REQUIRED, "No remote attempt exists for this fingerprint."
            )
        try:
            receipt = decode(ActionReceipt, self.vault.cipher().decrypt(path.read_bytes()))
            if receipt.fingerprint != identity or action_fingerprint(receipt.action) != identity:
                raise CampusError(
                    Code.SCOPE_DENIED, "Action receipt target does not match its path."
                )
            return receipt
        except InvalidToken:
            raise CampusError(Code.SCOPE_DENIED, "Action receipt integrity check failed.") from None
