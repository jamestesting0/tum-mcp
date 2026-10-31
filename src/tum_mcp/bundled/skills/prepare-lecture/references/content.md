# Authoring contract

Use `tum-mcp study schema lectures` for the installed authoritative schema.
Keep one course app, in its current app/ or legacy study/ layout. Author only the
requested lectures; preserve other workspaces and custom renderer files.

When preparation added/changed safe source receipts:

```sh
tum-mcp lecture export-snapshot PROJECT --output SNAPSHOT.json
tum-mcp study sync PROJECT --snapshot SNAPSHOT.json
```

This reconciles recording receipts as ordinary shared sources. It does not put
raw transcript/media into the app. Review conflicts and changed sources before
updating authored hashes. Do not fabricate a source hash, recording identity or
complete coverage to get a build through validation.

`lectures.json` has `schema_version: 2`, the bound `course_key`, `lectures` and
`evidence`. Each lecture has a stable key and title, the recording identity and date,
a `summary` (at most 600 characters), the exact source key/SHA versions, its checked-at
time, coverage, `notes` (up to 100) and `highlights` (up to 40) in recording order.
Either or both arrays may be empty; do not manufacture additions. Use the actual numeric
course/recording IDs plus the opaque course slug; they are not interchangeable.
Synthetic recordings belong only to a synthetic course.

Each note has a unique `key`, concise `text` (at most 600 characters), `evidence`
keys and optional `sources`/`pages` as below. Note and highlight keys share one
namespace per lecture. A note has no authored clip interval: its speech evidence
locates its recording source, shown only inside the source control. Optional `image`
uses the staged thumbnail object plus required descriptive `alt`; it is meaningful
content displayed with the note, not a decorative preview.

Each highlight has:

- `key`, `title` (at most 160 characters) and `interval: {start_s, end_s}` on the
  original recording clock, inside processed time;
- `teaches`: one sentence of at most 400 characters;
- `points`: at most three, each at most 300 characters;
- optional `sources` (course materials such as slides or a script, declared on the
  lecture) and `pages` for the first of them;
- `evidence`: the keys it rests on;
- `thumbnail`: the object printed by `lecture thumbnail`, with `evidence` set to its
  frame evidence key.

Highlights do not overlap. Inline math uses `\( ... \)`; the builder uses the existing
safe math renderer. Do not repeat timestamps in titles or text; the app shows each
range and links it to the recording.

Evidence kinds are `subtitle`, `asr` and `frame`. Each item has the recording ID, an
original-time `interval: {start_s, end_s}` and the source key/SHA. Every highlight
cites at least one `subtitle` or `asr` item inside its own interval (usually one item
spanning it) and the `frame` item of its thumbnail; the thumbnail's capture time lies
inside both. Every note also needs speech evidence. If it has an image, declare its
frame evidence too; the capture lies inside that frame and a cited speech interval.
Note evidence need not align to complete passage edges, since it defines no clip.
`reviewed` reflects actual review, not inference completion. Remove orphan
evidence. State genuine recognition uncertainty.

Coverage partitions the actual recording into eligible/excluded time, and the
eligible time into processed/missing spans. Keep uncertainty within processed
spans. Complete lecture coverage requires no missing/uncertain time and completed semantic
review. Do not hide a tiny missing tail by rounding, equate "prepared audio" with
reviewed content, or fill source gaps from general model knowledge.

A thumbnail is a measured recording frame: a lossless PNG whose longest edge is at most
960 px, staged by `lecture thumbnail` in `.tum-mcp/lecture-assets/` with its hash,
dimensions, `captured_at_s` and optional crop. It must match the processor's capture
inventory or a reproducible crop/resize of it; never draw, edit or substitute one. If a
build reports a thumbnail as changed after an update, stage it again with
`lecture thumbnail`.

The builder manages selected image copies; it does not delete edited/unmanaged
files. All lecture images count toward publication's 16 MiB/100-file whole-site limits;
keep a lecture local when its images cannot fit an export. Source freshness and semantic
revision are separate: refreshed receipts or decorative highlight thumbnails need not
invalidate comments, while changed note text/meaningful images, titles, points or ranges
do. Do not reset comment anchors or silently resolve feedback during a rebuild.
