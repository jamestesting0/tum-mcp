"""Bounded live retrieval from server-accessible channels; no message cache."""

import hashlib
import json
import time
from urllib.parse import quote

from bs4 import BeautifulSoup

from tum_mcp.errors import CampusError, Code
from tum_mcp.parsing import decode
from tum_mcp.transport import API
from tum_mcp.zulip.models import (
    Channel,
    Channels,
    CitedMessage,
    Cursor,
    Identity,
    ListCursor,
    MessagePage,
    Messages,
    Query,
    ServerSettings,
    Topics,
)


class Zulip:
    def __init__(self, api: API) -> None:
        self.api = api

    def settings(self) -> ServerSettings:
        return decode(ServerSettings, self.api.get("/api/v1/server_settings"))

    def identity(self) -> Identity:
        identity = decode(Identity, self.api.get("/api/v1/users/me"))
        if str(identity.user_id) != self.api.account.principal:
            raise CampusError(Code.SCOPE_DENIED, "Zulip credential identity changed; reconnect.")
        return identity

    def channels(self) -> Channels:
        self.identity()
        result = decode(
            Channels,
            self.api.get(
                "/api/v1/streams",
                {
                    "include_public": "true",
                    "include_subscribed": "true",
                },
            ),
        )
        return result.model_copy(
            update={"streams": tuple(sorted(result.streams, key=lambda stream: stream.stream_id))}
        )

    def page[T](
        self, items: tuple[T, ...], scope: str, cursor: str | None
    ) -> tuple[tuple[T, ...], str | None]:
        offset = 0
        if cursor:
            value = decode(ListCursor, cursor.encode())
            if value.account_id != self.api.account.id or value.scope != scope:
                raise CampusError(Code.SCOPE_DENIED, "Metadata cursor scope does not match.")
            offset = value.offset
        following = None
        if offset + 100 < len(items):
            following = ListCursor(
                account_id=self.api.account.id, scope=scope, offset=offset + 100
            ).model_dump_json()
        return items[offset : offset + 100], following

    def channel_page(self, cursor: str | None = None) -> Channels:
        channels = self.channels()
        items, following = self.page(channels.streams, "channels", cursor)
        return channels.model_copy(
            update={"streams": items, "next_cursor": following, "truncated": following is not None}
        )

    def require_channel(self, channel_id: int) -> Channel:
        for channel in self.channels().streams:
            if channel.stream_id == channel_id:
                return channel
        raise CampusError(Code.SCOPE_DENIED, "Channel not discoverable for this identity.")

    def topics(self, channel_id: int, cursor: str | None = None) -> Topics:
        self.require_channel(channel_id)
        result = decode(Topics, self.api.get(f"/api/v1/users/me/{channel_id}/topics"))
        items, following = self.page(result.topics, f"topics:{channel_id}", cursor)
        return result.model_copy(
            update={"topics": items, "next_cursor": following, "truncated": following is not None}
        )

    def messages(self, query: Query, *, message_id: int | None = None) -> MessagePage:
        self.require_channel(query.channel_id)
        fingerprint = hashlib.sha256(
            (
                self.api.account.id
                + query.model_dump_json(exclude={"cursor", "limit", "max_chars"})
            ).encode()
        ).hexdigest()
        anchor = "newest"
        if query.cursor:
            cursor = decode(Cursor, query.cursor.encode())
            if cursor.scope != fingerprint:
                raise CampusError(
                    Code.SCOPE_DENIED, "Cursor belongs to a different query or account."
                )
            anchor = str(cursor.anchor)
        narrow: list[dict[str, str | int]] = [{"operator": "stream", "operand": query.channel_id}]
        for operator, operand in (
            ("topic", query.topic),
            ("search", query.query),
            ("after", query.after),
            ("before", query.before),
        ):
            if operand is not None and operand != "":
                narrow.append({"operator": operator, "operand": operand})
        params = {
            "narrow": json.dumps(narrow),
            "anchor": str(message_id) if message_id else anchor,
            "num_before": "0" if message_id else str(query.limit),
            "num_after": "0",
            "include_anchor": "true" if message_id else "false",
            "apply_markdown": "true",
        }
        batch = decode(Messages, self.api.get("/api/v1/messages", params))
        if batch.ignored_parameters_unsupported:
            raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Server ignored a retrieval parameter.")
        cited: list[CitedMessage] = []
        remaining = query.max_chars
        for item in batch.messages:
            if item.type != "stream" or item.stream_id != query.channel_id:
                raise CampusError(
                    Code.SCOPE_DENIED, "Server returned a message outside the channel."
                )
            if message_id and item.id != message_id:
                raise CampusError(Code.SCOPE_DENIED, "Server returned a different message.")
            text = BeautifulSoup(item.content, "html.parser").get_text("\n", strip=True)
            snippet = text[: min(4000, remaining)]
            remaining -= len(snippet)
            cited.append(
                CitedMessage(
                    id=item.id,
                    channel_id=query.channel_id,
                    topic=item.subject,
                    sender_id=item.sender_id,
                    author=item.sender_full_name,
                    timestamp=item.timestamp,
                    text=snippet,
                    truncated=len(text) > len(snippet),
                    source_link=(
                        f"{self.api.account.origin}/#narrow/channel/{query.channel_id}"
                        f"/topic/{quote(item.subject, safe='')}/near/{item.id}"
                    ),
                )
            )
        next_cursor = None
        if not batch.found_oldest and not message_id and cited:
            next_anchor = min(item.id for item in cited)
            if query.cursor and next_anchor >= int(anchor):
                raise CampusError(Code.INVALID_RESPONSE, "Pagination made no progress.")
            next_cursor = Cursor(anchor=next_anchor, scope=fingerprint).model_dump_json()
        partial = bool(next_cursor) or (not batch.found_oldest and not message_id)
        return MessagePage(
            account_id=self.api.account.id,
            instance_id=self.api.account.origin,
            channel_ids=(query.channel_id,),
            topic=query.topic,
            requested_after=query.after,
            requested_before=query.before,
            query=query.query,
            returned_count=len(cited),
            next_cursor=next_cursor,
            truncated=partial or any(item.truncated for item in cited),
            oldest_returned_at=min((item.timestamp for item in cited), default=None),
            newest_returned_at=max((item.timestamp for item in cited), default=None),
            fetched_at=time.time(),
            history_limit_known=batch.history_limited is not None,
            coverage_status="history_limited"
            if batch.history_limited
            else "partial"
            if partial
            else "page_complete",
            limitations=("Live retained history only; concurrent edits/deletions are possible.",),
            messages=tuple(cited),
        )
