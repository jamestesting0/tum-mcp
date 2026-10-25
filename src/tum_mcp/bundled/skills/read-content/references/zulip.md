# Zulip reading

Reuse known channel IDs. If the mapping is missing, read `tum_get_preferences`
or `tum_resolve_course`; use `zulip_list_channels` for metadata when necessary.
Confirm ambiguous mappings. Do not infer permission from a similar course title.

Use `zulip_search_messages` with one enabled `search.channel_id`, a focused
query and date bounds when relevant. Follow `next_cursor` when coverage matters.
Expand decisive context with `zulip_read_topic`; re-fetch an important claim
with `zulip_get_message`. Use `zulip_list_topics` for course inventory, not as a
substitute for searching message content.

For catch-up, use the requested period, or the local `zulip_get_checkpoint` and
configured window. Respect muted topics. Group by topic, cite message links and
dates, and distinguish verified instructor advice from student claims. Advance
`zulip_save_checkpoint` only after the complete selected scope is summarized.
This stores local message IDs; it does not change unread state on Zulip.

Do not read DMs, post, react, mark messages read, or change subscriptions/settings.
Do not store author/contact details in a generated site unless the user needs
them. A compact cited clarification usually belongs in materials/other/.
