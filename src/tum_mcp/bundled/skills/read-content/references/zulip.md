# Zulip

Reuse channel IDs or an existing mapping. Resolve missing mappings with
`tum_get_preferences`/`tum_resolve_course`; use `zulip_list_channels` for discovery.
Similar names do not establish course identity or message permission.
Public and subscribed private channels returned by the server need no local grant.
Prefer the relevant current-semester channel and requested time window; check
channel/topic metadata before reading history. Keep cursors tied to their query.

For facts, call `zulip_search_messages` with search.channel_id, a focused query,
relevant dates and bounded limit/max_chars. Expand decisive context with
`zulip_read_topic`. Use `zulip_get_message` when a cited result is stale or clipped.
If still clipped, use a permitted read-only view of that cited message or report
what is missing; older-page pagination cannot recover a clipped message's tail.

For catch-up, use the requested period or configured window/checkpoint via
`zulip_get_checkpoint`; respect muted topics. Scan newest results toward the
cutoff, deduplicate message IDs, and follow cursors with unchanged filters.
A previous older-page cursor will miss new arrivals. Topic inventory uses
`zulip_list_topics`; it does not replace message search. Save
`zulip_save_checkpoint` only after the requested catch-up scope is fully summarized.
This checkpoint is local and does not mark messages read.

Cite links/dates and attribute claims without guessing instructor roles from
names. Retained-history/truncation limits qualify completeness. No DMs, posting,
reactions or read/subscription changes. Store only needed cited clarifications,
not unnecessary author/contact details.
