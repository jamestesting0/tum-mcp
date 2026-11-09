# Prepared course to maintained audio

## Inputs and scope

Read AGENTS.md, the Study files under app/study/ or the Exam files under app/exam/,
relevant .tum-mcp/state.json entries and existing audio records. Use the content schema already used by prepare-study;
`tum-mcp study schema content` describes unfamiliar fields. Reuse an existing source
check; otherwise `tum-mcp study inspect PROJECT` identifies stale units without
refreshing campus websites. A hash mismatch requires content review by
prepare-study, not an automatic rebind by audio-notes.

The prepared website is the only course-content input. Read its structured content
rather than scraping rendered HTML or reopening raw PDFs/Notion pages. Include
distinct concepts and qualifications found in its flashcards and correct practice
feedback; do not read every duplicate card or distractor aloud. Keep erroneous
answer options clearly identified as misconceptions if they are discussed.

If a requested website has not been prepared, complete prepare-study first when
the user's request includes that work. An audio-only request does not authorize
new course authoring, source refreshes, publication or campus actions. Continue
unblocked categories and report any unavailable or stale inputs.

## Single output root

Use PROJECT/audio/ directly. Do not add another course-named wrapper directory.

```text
audio/
  README.md                  Playback, actual voice, durations and update instructions
  SOURCES.md                 Prepared content identity and original source locators
  COVERAGE.md                Current coverage and unresolved gaps
  manifest.json              Published category receipts (written by publish)
  plan.json                  Desired categories, hashes and pending changes (publish keeps it current)
  voice.json                 Voice profiles: provider, route, voice, language, model, settings
  playlist.m3u               Relative tracks/ paths in the intended study order (publish)
  categories/01_category.json  The category script you write and check
  scripts/01_category.txt    Published editable narration
  tracks/01_category.m4a     One published audio file per category
  chapters/01_category.json  Section titles and measured start/end seconds
  .build/                    Candidates, chunks, downloads, logs and QA evidence
  archive/                   Recoverable superseded published files and receipts
```

Use matching stems across scripts, tracks and chapters. New stems use a minimum
two-digit numeric prefix and lowercase ASCII words separated by hyphens, such as
01_security-foundations. Assign a stable category key separately from its title.
Preserve existing stems/prefixes, even across title or playlist-order changes;
append unused numbers for new categories instead of renumbering existing files.
Disambiguate colliding slugs with the category key. Playlist order follows the
course sequence; it need not match a newly changed numeric order.

Use relative POSIX paths for course artifacts in records and playlists, all confined
to audio/, including on Windows. Reject absolute paths, parent traversal and
symlinks that escape that root. Preserve unrecognized files; do not treat the
directory as disposable. Configure speech downloads and temporary course outputs
under .build/. If a browser forces its own temporary download location, immediately
move the returned file into .build/ and leave no additional speech artifacts there.
Reusable model downloads and runtimes are the exception: use the host's shared
user storage in [local Kokoro setup](kokoro.md), not per-project copies. Track shared
dependencies by version/hash separately from course artifact paths. Provider
credentials stay in the established secret store/environment, never in audio/.

## Stable categories and complete coverage

Reuse meaningful category groups from the website's outline and unit paths for
Study tracks, and the Exam topics in sheet order for cheatsheet tracks. Where there
are no groups, use existing topics. Do not create new subject categories or group
unrelated units merely to shorten the playlist. Every current unit, entry and pattern
has exactly one primary category; brief spoken prerequisite reminders may repeat a
concept without duplicating whole units.

`sources` prints each Study unit's block, objective, flashcard and question
locators with fingerprints, and each cheatsheet entry and pattern as one locator.
Copy them into the chapter that teaches them. Blocks have no stable IDs, so an
index alone cannot prove identity after insertions; `check` compares the copied
fingerprint with the current content. Map each substantive concept, definition,
nonredundant example, mechanism, condition, comparison and limitation to a named
chapter. Duplicate source explanations may share one spoken treatment; say in the
teaching review which locators were consolidated and why no distinct teaching was
lost. A concept being named is not evidence that it has been explained. COVERAGE.md
lists `study_required` limits and anything still unpublished.

## Change detection and receipts

`publish` computes every fingerprint and receipt: the semantic hash of each Study
unit (teaching content, not layout, citations or navigation) or Exam item
(everything but its citations), the category hash over its title and ordered units,
exact file hashes, the voice profile, narration chunk hashes and the validation
evidence. `study report PROJECT --section review` reads them back and marks a track
stale when its sources' teaching changes. Do not compute or edit these records by
hand.

Keep actual profiles per category; voice.json's preferred/fallback policy is not
proof that a track used that provider. On authorized Kokoro fallback, mark the
affected category's old-provider chunks ineligible for the new candidate and
generate that whole category with the selected Kokoro profile. Reuse unaffected
published categories. Record the fallback reason and pending/completed state under
.build/ so interrupted runs resume without retrying a known ElevenLabs gate.

Check the teaching review for every requested category before deciding reuse,
including metadata-only updates. Missing evidence or changed narration guidance
requires the review below even when the source and audio hashes still match.

| Comparison with published receipt | Required action |
| --- | --- |
| No receipt or new category | Write and generate the new category. |
| Added/changed teaching within a category | Revise its narration and affected chunks, then assemble a complete replacement track. |
| Authorized provider fallback for a category | Regenerate the full category with one profile; retain the previous usable track until validation succeeds. |
| Content removed or moved | Reconcile both affected categories and their coverage; retire empty categories from the active playlist with recoverable archives. |
| Only source references or navigation order changed | Review provenance/mapping and update records/playlist without resynthesizing identical speech. |
| Same inputs, profile, valid published file hashes and current teaching review | Reuse the existing category. |
| Teaching review absent or narration guidance changed | Review the existing script; backfill evidence if it passes, otherwise revise only affected speech and regenerate the changed chunks. |
| Missing, corrupt or externally edited file | Regenerate missing/corrupt output; preserve and reconcile personal edits before replacing them. |
| Script exists but track is absent/unverified | Resume generation; coverage is still pending. |

When no manifest exists, preserve any existing files as unverified and plan current
targets. Do not infer coverage, provider identity or an adoption/migration workflow
from filenames.

## Generation, validation and publication

Write the category script first and run `check`; it is the only place sentences,
chapters and coverage live. Complete the [teaching check](narration.md#teaching-check-before-synthesis)
on the whole script before synthesis, then keep a concise
`.build/STEM/teaching-review.md`: units, chapter-to-locator mapping, consolidation
decisions, `study_required` limits, word count, and the failed checks you repaired.
Write "not applicable" for checks with no relevant source material; never invent
recall prompts or a numerical learning score. Fix clear in-scope problems yourself.

`narration` names one file per sentence; its name hashes the text and the voice
profile, so an edited sentence or a changed profile needs a new file and unchanged
sentences are reused. For a new voice/profile, test a short passage first (voice
guidance). Validate each generated file's start and end against its sentence; a
plausible duration does not prove the whole sentence was spoken. Use available
transcription or listening tools when you have them and keep their output under
`.build/`.

`publish` does the rest and refuses anything it cannot verify: missing or stale
coverage, unspeakable sentences, absent narration files, a track that is not AAC
M4A, does not decode, misses -16 LUFS by more than 1 LU, exceeds -1.5 dBTP or whose
embedded chapters differ from the script. It archives the previous published files
under `archive/`, installs the new track, script and chapters, writes the
validation evidence and the manifest receipt last, and rebuilds the playlist. Never
hand-write `manifest.json` or `plan.json`; edit the category script and publish
again. Update README.md and COVERAGE.md from the published receipts.

A published track has signal, script and coverage evidence, not listening
evidence. Publish it anyway: the student asked for audio. Report what was and was
not heard; the media review keeps delivery unscored until someone listens.

## Explore boundary

Default category lessons use core blocks, cards and correct practice feedback.
Exclude `Unit.explore` from required narration, minutes and core coverage claims.
Do not silently promote optional context; an explicit request for supplementary audio
needs its own stated scope. See [Explore](../../prepare-study/references/explore.md).
