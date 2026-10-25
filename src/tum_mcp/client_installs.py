"""Local ownership receipts and reversible writes for managed client installations."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from pydantic import Field, JsonValue, ValidationError, model_validator

from tum_mcp.client_hosts import ClientHost
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen, config_path
from tum_mcp.skill_catalog import CURRENT_SKILLS, LEGACY_SKILLS

ClientName = Literal["codex", "claude", "cursor", "antigravity", "generic"]
MANAGED_ROOTS: Final = {
    "codex": ".codex/plugins/local/tum-mcp",
    "claude": ".claude/skills",
    "cursor": ".cursor/skills",
    "antigravity": ".gemini/config/skills",
}


class Installation(Frozen):
    schema_version: Literal[1] = 1
    client: ClientName
    host: ClientHost
    home: Path
    version: str
    server: dict[str, JsonValue]
    files: dict[str, str] = Field(default_factory=dict, max_length=1000)
    catalog: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def confined_files(self) -> "Installation":
        prefix = MANAGED_ROOTS.get(self.client)
        skill_index = len(PurePosixPath(prefix).parts) if prefix else 0
        if not self.home.is_absolute():
            raise CampusError(Code.WORKSPACE_CONFLICT, "Installation home must be absolute.")
        for name, digest in self.files.items():
            path = PurePosixPath(name)
            if (
                prefix is None
                or not name.startswith(prefix + "/")
                or (
                    self.client in {"claude", "cursor", "antigravity"}
                    and (
                        len(path.parts) < skill_index + 2
                        or path.parts[skill_index] not in {*CURRENT_SKILLS, *LEGACY_SKILLS}
                    )
                )
                or ".." in path.parts
                or path.is_absolute()
                or "\\" in name
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise CampusError(Code.WORKSPACE_CONFLICT, "Invalid managed installation paths.")
        return self


def receipt_path(client: str, host: ClientHost, home: Path) -> Path:
    identity = hashlib.sha256(f"{client}\0{host}\0{home.resolve()}".encode()).hexdigest()
    return config_path() / "clients" / f"{identity}.json"


def load_receipt(client: str, host: ClientHost, home: Path) -> Installation | None:
    path = receipt_path(client, host, home)
    if not path.exists():
        return None
    try:
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Invalid managed installation record.")
        receipt = Installation.model_validate_json(path.read_bytes())
        if (receipt.client, receipt.host, receipt.home) != (client, host, home.resolve()):
            raise CampusError(Code.WORKSPACE_CONFLICT, "Installation record does not match client.")
        return receipt
    except (OSError, ValidationError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Installation record is unreadable; preserve and review it."
        ) from None


def read_owned_file(path: Path, home: Path) -> bytes | None:
    relative = path.relative_to(home)
    current = home
    for part in relative.parts:
        current /= part
        if current.is_symlink() or current.is_junction():
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "A symbolic link in client paths was preserved."
            )
    if path.exists() and not path.is_file():
        raise CampusError(Code.WORKSPACE_CONFLICT, "A client file path is occupied by a directory.")
    return path.read_bytes() if path.is_file() else None


@dataclass(frozen=True, slots=True)
class Write:
    path: Path
    before: bytes | None
    after: bytes | None


def managed_writes(
    home: Path, desired: dict[str, bytes], previous: Installation | None
) -> tuple[Write, ...]:
    old = previous.files if previous else {}
    writes: list[Write] = []
    for name in sorted(set(old) | set(desired)):
        target = home / name
        before = read_owned_file(target, home)
        after = desired.get(name)
        if before == after:
            continue
        digest = hashlib.sha256(before).hexdigest() if before is not None else None
        if name in old:
            if digest != old[name]:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    f"Customized or removed client file preserved: {name}. "
                    "Review it before updating.",
                )
        elif before is not None:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, f"Existing customized file preserved: {name}."
            )
        writes.append(Write(target, before, after))
    return tuple(writes)


def commit_writes(writes: tuple[Write, ...]) -> None:
    """Preflight all writes, then restore our changes if an ordinary I/O failure occurs."""
    applied: list[Write] = []
    try:
        for item in writes:
            actual = item.path.read_bytes() if item.path.is_file() else None
            if item.path.is_symlink() or actual != item.before:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Client files changed during setup; retry."
                )
        for item in writes:
            if item.before == item.after:
                continue
            item.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if item.after is None:
                item.path.unlink()
            else:
                private_write(item.path, item.after)
            applied.append(item)
    except (OSError, CampusError):
        recovered = True
        for item in reversed(applied):
            try:
                actual = item.path.read_bytes() if item.path.is_file() else None
                if actual != item.after or item.path.is_symlink():
                    recovered = False
                    continue
                if item.before is None:
                    item.path.unlink(missing_ok=True)
                else:
                    private_write(item.path, item.before)
            except OSError:
                recovered = False
        message = (
            "Client update failed; previous files were restored. Check permissions and retry."
            if recovered
            else "Client update was interrupted; some files need local review before retrying."
        )
        raise CampusError(Code.WORKSPACE_CONFLICT, message) from None


def prune_removed_folders(home: Path, removed_files: tuple[str, ...]) -> None:
    """Prune only ancestors of removed managed files, preserving every nonempty folder."""
    import errno

    directories: set[Path] = set()
    for name in removed_files:
        relative = PurePosixPath(name)
        boundary = (
            home
            / {
                ".codex": ".codex/plugins/local",
                ".claude": MANAGED_ROOTS["claude"],
                ".cursor": MANAGED_ROOTS["cursor"],
                ".gemini": MANAGED_ROOTS["antigravity"],
            }[relative.parts[0]]
        )
        parent = (home / name).parent
        while parent != boundary and parent.is_relative_to(boundary):
            directories.add(parent)
            parent = parent.parent
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError as error:
            if error.errno not in {errno.ENOTEMPTY, errno.ENOENT}:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    "Managed files changed, but empty directories need local cleanup.",
                ) from None


def require_supported_version(previous: Installation, current: str) -> None:
    if previous.version == "legacy":
        return
    installed = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", previous.version)
    requested = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", current)
    if installed is None or requested is None:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Installation version needs local review before refresh."
        )
    if tuple(map(int, installed.groups())) > tuple(map(int, requested.groups())):
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "A newer managed client version is installed. Use its package to update or "
            "unregister the client before an intentional rollback.",
        )
