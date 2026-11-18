"""Ask agent chats: one private file per chat, the newest 50 per course."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tum_mcp.course.project.store import private_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write

KEEP = 50
Text = Annotated[str, Field(max_length=40000)]


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    sections: tuple[str, ...] = ()
    summary: Annotated[str, Field(max_length=400)] = ""
    undone: bool = False


class Step(BaseModel):
    """One line of an agent's work log: a step it took, a note it wrote before a tool call, or
    a spell of thinking with its length and, where the agent shares one, a short summary."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["step", "note", "thinking"]
    text: Annotated[str, Field(max_length=800)] = ""
    seconds: int = 0


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["student", "agent"]
    text: Text
    at: datetime
    quote: Annotated[str, Field(max_length=2000)] = ""
    section: Annotated[str, Field(max_length=200)] = ""
    change: Change | None = None
    log: tuple[Step, ...] = ()
    worked: int = 0


class Chat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    provider: Literal["claude", "codex", "cursor"]
    profile: str = ""
    session: str = ""
    title: Annotated[str, Field(max_length=200)] = ""
    place: Annotated[str, Field(max_length=200)] = ""
    route: Annotated[str, Field(max_length=200)] = ""
    anchor: dict | None = None
    context: str = ""
    created: datetime
    updated: datetime
    messages: tuple[Message, ...] = ()


def _folder(root: Path) -> Path:
    return private_path(root, "agent/threads")


def _lock(root: Path) -> FileLock:
    folder = _folder(root)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return FileLock(str(folder / ".lock"))


def _path(root: Path, chat: UUID) -> Path:
    return _folder(root) / f"{chat}.json"


def _load(path: Path) -> Chat | None:
    try:
        return Chat.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        return None


def create(
    root: Path,
    provider: Literal["claude", "codex", "cursor"],
    *,
    title: str,
    place: str,
    route: str,
    anchor: dict | None,
) -> Chat:
    now = datetime.now(UTC)
    chat = Chat(
        id=uuid4(),
        provider=provider,
        title=title[:200],
        place=place[:200],
        route=route[:200],
        anchor=anchor,
        created=now,
        updated=now,
    )
    return save(root, chat)


def read(root: Path, chat: UUID) -> Chat:
    found = _load(_path(root, chat))
    if found is None:
        raise CampusError(Code.STALE_RESULT, "This chat no longer exists.")
    return found


def save(root: Path, chat: Chat) -> Chat:
    chat = chat.model_copy(update={"updated": datetime.now(UTC)})
    with _lock(root):
        private_write(_path(root, chat.id), chat.model_dump_json(indent=1).encode())
        for old in _summaries(root)[KEEP:]:
            _path(root, UUID(old["id"])).unlink(missing_ok=True)
    return chat


def append(root: Path, chat: Chat, message: Message) -> Chat:
    return save(root, chat.model_copy(update={"messages": (*chat.messages, message)}))


def delete(root: Path, chat: UUID) -> None:
    with _lock(root):
        _path(root, chat).unlink(missing_ok=True)


def _summaries(root: Path) -> list[dict]:
    chats = [chat for path in _folder(root).glob("*.json") if (chat := _load(path))]
    chats.sort(key=lambda chat: chat.updated, reverse=True)
    return [
        {
            "id": str(chat.id),
            "title": chat.title,
            "place": chat.place,
            "updated": chat.updated.isoformat(),
        }
        for chat in chats
    ]


def listing(root: Path) -> list[dict]:
    if not _folder(root).exists():
        return []
    with _lock(root):
        return _summaries(root)


def public(chat: Chat) -> dict:
    return json.loads(chat.model_dump_json(exclude={"session"}))
