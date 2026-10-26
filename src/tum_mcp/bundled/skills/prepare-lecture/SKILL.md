---
name: prepare-lecture
description: Prepare or update the Lecture Notes workspace in a local TUM course app from selected recordings, timed transcripts and course materials, emphasizing the professor's additional teaching. General course lessons and practice use prepare-study.
---

# Prepare Lecture

Create useful, timestamped notes about what the professor adds to the course
materials: reasoning, caveats, examples, corrections, explanations and advice.
Keep Lecture Notes distinct from the Study workspace. Do not add assessments or
expand the recording into a replacement textbook.

The optional Lecture extension must be installed with `tum-mcp install lecture`.
Read the bound project's `.tum-mcp/course.md` and state first. Use sync-course
when the course or its verified TUM-Live binding has not been initialized.
Process only the recordings the user selected. Campus services stay read-only.

Use `tum-mcp lecture inspect PROJECT` to reuse prepared evidence offline, with
its as-of date. For missing evidence, run
`tum-mcp lecture prepare PROJECT --recording URL`. Prefer existing timed captions
and relevant verified lecture materials. Imported original-time WebVTT uses
`--transcript PATH`. Whole-silent recordings are invalid: stop processing them.
Missing speech, source material or recognition capability remains a real gap.

Preparation fetches no preview images by default. Use `--previews` only to locate
a visual question; it does not authorize whole-video vision analysis.

Read the entire retained transcript through bounded `lecture transcript` pages
with `--recording KEY --start SECONDS --end SECONDS --limit N --offset N`.
Text pages omit word-level detail by default; use `--words` only for alignment
review. Compare the transcript with the supplied course materials before selecting teaching points.
Do not claim a point is absent from materials that were unavailable for comparison.
Request a full frame through `prepare --frame-at SECONDS` only when text and
materials cannot resolve critical notation, a live derivation or demonstration.
Seek previews are approximate candidates; final recording figures need measured
capture times. Generated supporting diagrams are ordinary explanatory content,
never recording-frame evidence.

Export safe recording sources with `lecture export-snapshot PROJECT --output PATH`
and reconcile them with `study sync PROJECT --snapshot PATH` when needed.
Read `study schema lectures`; author coherent notes in `app/lectures.json`
(or the existing legacy `study/` layout), keeping real coverage, source hashes and
reviewed evidence. Stage selected verified figures in `.tum-mcp/lecture-assets/`.
Keep attribution and added-explanation review details private; the reading UI
should have clear notes, useful formulas/visuals and unobtrusive timestamp links,
without AI-added labels. Do not attribute unsupported claims to the professor.

Build once with `tum-mcp study build PROJECT --local-only`, then check the actual
notes, figures and timestamp destinations. Preserve existing authoring and user
files on failures. Report unresolved coverage honestly. Publishing requires the
separate publish-course workflow and explicit inclusion of lecture notes.
