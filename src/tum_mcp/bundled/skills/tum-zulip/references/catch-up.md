# Catch-up and checkpoints

Use the requested period. If none is supplied, read `zulip_get_checkpoint` and
honor the configured catch-up window and muted topics. Search each selected
channel using `after`/`before` dates, follow `next_cursor`, and expand only topics
needed for the digest.

Group the summary by topic with dates and message permalinks. An empty result
means no matches in the searched scope. Advance `zulip_save_checkpoint` only
when that scope was completely retrieved and summarized; save message IDs,
never conversation text. An incomplete pass must not consume the checkpoint.
