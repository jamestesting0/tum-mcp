"""Account-bound TUMonline read policy, independent of legacy preferences."""

import re
from enum import StrEnum
from pathlib import Path
from typing import Final

from filelock import FileLock
from pydantic import Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen, config_dir, config_path

ACCOUNT_PATTERN: Final = re.compile(r"[a-f0-9]{64}")
MAX_POLICY_BYTES: Final = 16 * 1024


class Scope(StrEnum):
    STUDIES_COURSES = "studies_courses"
    ACADEMIC_PROGRESS = "academic_progress"
    EXAMS = "exams"
    ADMISSION = "admission"


LABELS: Final = {
    Scope.STUDIES_COURSES: "Studies and courses",
    Scope.ACADEMIC_PROGRESS: "Grades and progress",
    Scope.EXAMS: "Exams",
    Scope.ADMISSION: "Admission",
}


class Policy(Frozen):
    schema_version: int = Field(ge=1, le=1, strict=True)
    account_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(ge=0, strict=True)
    allowed: frozenset[Scope]

    def allows(self, scope: Scope) -> bool:
        return scope in self.allowed

    def require(self, scope: Scope) -> None:
        if scope not in self.allowed:
            raise CampusError(
                Code.SCOPE_DENIED,
                f'TUMonline "{LABELS[scope]}" is off; allow it with tum-mcp manage tumonline.',
            )


def updated_policy(policy: Policy, allowed: frozenset[Scope]) -> Policy:
    """Validate scope replacements before committing them to disk."""
    try:
        return Policy(
            schema_version=policy.schema_version,
            account_id=policy.account_id,
            revision=policy.revision + 1,
            allowed=allowed,
        )
    except ValidationError:
        raise CampusError(Code.SCOPE_DENIED, "Invalid TUMonline scope selection.") from None


class PolicyStore:
    """Serialize each account's permission changes without touching existing preferences."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else config_dir() / "tumonline"
        if self.root.is_symlink() or self.root.is_junction():
            raise CampusError(Code.SCOPE_DENIED, "TUMonline policy directory cannot be a symlink.")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)

    def _path(self, account_id: str) -> Path:
        if not ACCOUNT_PATTERN.fullmatch(account_id):
            raise CampusError(Code.SCOPE_DENIED, "Invalid TUMonline account identifier.")
        return self.root / f"{account_id}.json"

    @staticmethod
    def _read(path: Path, account_id: str) -> Policy:
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise CampusError(Code.SCOPE_DENIED, "TUMonline policy must be a regular local file.")
        try:
            with path.open("rb") as stream:
                body = stream.read(MAX_POLICY_BYTES + 1)
            if len(body) > MAX_POLICY_BYTES:
                raise CampusError(Code.SCOPE_DENIED, "TUMonline policy exceeds its size limit.")
            policy = Policy.model_validate_json(body)
        except (ValidationError, OSError):
            raise CampusError(
                Code.SCOPE_DENIED, "TUMonline policy is missing or invalid."
            ) from None
        if policy.account_id != account_id:
            raise CampusError(Code.SCOPE_DENIED, "TUMonline policy account mismatch.")
        return policy

    @classmethod
    def snapshot(cls, root: Path | None = None) -> tuple[Policy, ...]:
        """Read atomically saved policies without creating directories or lock files."""
        directory = root if root is not None else config_path() / "tumonline"
        if directory.is_symlink() or directory.is_junction():
            raise CampusError(Code.SCOPE_DENIED, "TUMonline policy directory cannot be a symlink.")
        return tuple(
            cls._read(path, path.stem)
            for path in sorted(directory.glob("*.json"))
            if ACCOUNT_PATTERN.fullmatch(path.stem)
        )

    def read(self, account_id: str) -> Policy:
        path = self._path(account_id)
        with FileLock(str(path.with_suffix(".lock"))):
            return self._read(path, account_id)

    def create(self, account_id: str) -> Policy:
        """Create policy only as part of a verified new account transaction."""
        path = self._path(account_id)
        with FileLock(str(path.with_suffix(".lock"))):
            if path.exists() or path.is_symlink():
                raise CampusError(Code.SCOPE_DENIED, "TUMonline policy already exists.")
            policy = Policy(
                schema_version=1,
                account_id=account_id,
                revision=0,
                allowed=frozenset({Scope.STUDIES_COURSES}),
            )
            private_write(path, policy.model_dump_json().encode())
            return policy

    def set_scope(self, account_id: str, scope: Scope, allowed: bool) -> Policy:
        path = self._path(account_id)
        with FileLock(str(path.with_suffix(".lock"))):
            policy = self._read(path, account_id)
            scopes = policy.allowed | {scope} if allowed else policy.allowed - {scope}
            if scopes == policy.allowed:
                return policy
            updated = updated_policy(policy, scopes)
            private_write(path, updated.model_dump_json().encode())
            return updated

    def accounts(self) -> tuple[str, ...]:
        """List only policy file names, validating every record before showing it."""
        ids = tuple(
            sorted(
                path.stem
                for path in self.root.glob("*.json")
                if ACCOUNT_PATTERN.fullmatch(path.stem)
            )
        )
        for account_id in ids:
            self.read(account_id)
        return ids

    def save_scopes(self, previous: Policy, allowed: frozenset[Scope]) -> Policy:
        """Atomically apply a reviewed scope selection, rejecting stale policy views."""
        path = self._path(previous.account_id)
        with FileLock(str(path.with_suffix(".lock"))):
            current = self._read(path, previous.account_id)
            if current != previous:
                raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; review again.")
            if allowed == current.allowed:
                return current
            updated = updated_policy(current, allowed)
            private_write(path, updated.model_dump_json().encode())
            return updated
