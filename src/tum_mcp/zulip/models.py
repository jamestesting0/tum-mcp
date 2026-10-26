"""Zulip wire models and bounded, cited tool responses."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tum_mcp.settings import Frozen, PositiveId


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class ServerSettings(Wire):
    zulip_version: str
    zulip_feature_level: int = 0
    realm_url: str = ""


class Identity(Wire):
    user_id: PositiveId
    email: str
    is_guest: bool = False


class Channel(Wire):
    stream_id: PositiveId
    name: str
    invite_only: bool = False
    history_public_to_subscribers: bool = False
    is_archived: bool = False
    content_access: Literal["not_checked"] = "not_checked"


class Channels(Wire):
    streams: tuple[Channel, ...]
    next_cursor: str | None = None
    truncated: bool = False


class Topic(Wire):
    name: str
    max_id: PositiveId


class Topics(Wire):
    topics: tuple[Topic, ...]
    next_cursor: str | None = None
    truncated: bool = False


class Message(Wire):
    id: PositiveId
    type: Literal["stream", "private"]
    stream_id: PositiveId | None = None
    subject: str = ""
    content: str
    sender_id: PositiveId
    sender_full_name: str
    timestamp: int


class Messages(Wire):
    messages: tuple[Message, ...] = Field(max_length=100)
    found_oldest: bool
    found_newest: bool
    history_limited: bool | None = None
    ignored_parameters_unsupported: tuple[str, ...] = ()


class Query(Frozen):
    channel_id: PositiveId
    query: str = Field(default="", max_length=500)
    topic: str | None = Field(default=None, max_length=500)
    after: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    before: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    cursor: str | None = Field(default=None, max_length=1000)
    limit: int = Field(default=50, ge=1, le=100)
    max_chars: int = Field(default=12000, ge=500, le=30000)


class Cursor(Frozen):
    anchor: PositiveId
    scope: str


class ListCursor(Frozen):
    account_id: str
    scope: str
    offset: int = Field(ge=0, le=100000)


class CitedMessage(Frozen):
    id: int
    channel_id: int
    topic: str
    sender_id: int
    author: str
    timestamp: int
    text: str
    truncated: bool
    source_link: str


class MessagePage(Frozen):
    account_id: str
    instance_id: str
    channel_ids: tuple[int, ...]
    topic: str | None
    requested_after: str | None
    requested_before: str | None
    query: str
    returned_count: int
    next_cursor: str | None
    truncated: bool
    oldest_returned_at: int | None
    newest_returned_at: int | None
    fetched_at: float
    coverage_status: str
    history_limit_known: bool
    limitations: tuple[str, ...]
    messages: tuple[CitedMessage, ...]
    untrusted_content: bool = True
