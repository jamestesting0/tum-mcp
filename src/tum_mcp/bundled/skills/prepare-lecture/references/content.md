# Authoring contract

Use `tum-mcp study schema lectures` for the installed authoritative schema.
Keep one course app, in its current app/ or legacy study/ layout. Author only the
requested lecture objects; preserve other workspaces and custom renderer files.

When preparation added/changed safe source receipts:

```sh
tum-mcp lecture export-snapshot PROJECT --output SNAPSHOT.json
tum-mcp study sync PROJECT --snapshot SNAPSHOT.json
```

This reconciles recording receipts as ordinary shared sources. It does not put
raw transcript/media into the app. Review conflicts and changed sources before
updating authored hashes. Do not fabricate a source hash, recording identity or
complete coverage to get a build through validation.

`lectures.json` has `schema_version: 1`, the bound `course_key`, `lectures` and
`evidence`. Each lecture includes a stable key/title, recording identity and date,
overview, takeaways, exact source key/SHA versions, checked-at time, coverage and
stable topic sections. Use the actual numeric course/recording IDs plus the
opaque course slug; they are not interchangeable. Synthetic recordings belong
only to a synthetic course.

Each section has a stable key/title, shared safe `blocks`, referenced `evidence`
keys and optional `figures`. Reuse text, formula, table, diagram, plot and code
blocks. Do not invent custom HTML, a new page system or assessment fields. Inline
math uses `\( ... \)`; formula blocks retain validated LaTeX and explain symbols
and conditions. The builder uses the existing safe math renderer.

Evidence kinds are subtitle, asr, frame or document. Timed evidence has the
recording ID and original-time `interval: {start_s, end_s}` plus source key/SHA.
Documents have an actual locator instead of a recording interval. Each teaching
section needs timed primary evidence in the processed retained span; supporting
material cannot replace it. Review flags reflect actual review, not inference
completion. Remove orphan evidence. State genuine recognition uncertainty.

Coverage partitions the actual recording into eligible/excluded time, and the
eligible time into processed/missing spans. Keep uncertainty within processed
spans. Complete notes require no missing/uncertain time and completed semantic
review. Do not hide a tiny missing tail by rounding, equate “prepared audio” with
reviewed notes, or fill source gaps from general model knowledge.

A captured figure cites frame evidence and has the reviewed image hash, confined
`lecture-assets/SHA.png` (or jpg/webp) path, dimensions, measured `captured_at_s`,
caption and descriptive alt text. Stage chosen bytes in
`.tum-mcp/lecture-assets/`. Real figures must match the processor's capture
inventory, or a reproducible crop/resize with original-image provenance. Inspect
the final asset: preserve critical notation legibly. Do not redraw it as evidence.
A necessary new explanatory visual uses an ordinary diagram block instead.

The builder manages selected image copies; it does not delete edited/unmanaged
files. Local asset limits differ from publication's 16 MiB/100-file whole-site
limits. Keep notes local if essential legible figures cannot fit an export.
Source freshness and semantic note revision are separate: a refreshed receipt or
re-encoded identical figure need not invalidate passage comments; changed prose
can. Do not reset comment anchors or silently resolve feedback during a rebuild.
