# Prepared course to maintained audio

## Inputs and scope

Read the course's AGENTS.md, study/content.json, relevant .study/state.json entries
and existing audio records. Use the content schema already used by prepare-study;
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
  manifest.json              Last verified published category receipts
  plan.json                  Current desired categories, hashes and pending changes
  voice.json                 Provider, access route, voice and synthesis settings
  playlist.m3u               Relative tracks/ paths in the intended study order
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

Reuse meaningful category groups from the website's outline and unit paths. Where
there are no groups, use its existing topics. Do not create new subject categories
or group unrelated units merely to shorten the playlist. Persist the mapping from
stable unit keys to category keys in plan.json and manifest.json. Reconcile moves
against the current outline, keeping category identity where it still represents
the same group. Every current unit has exactly one primary category; brief spoken
prerequisite reminders may repeat a concept without duplicating entire units.

For each unit record its key, learning-objective keys and block locators, such as
`blocks[2]` plus the block title and fingerprint. Blocks have no stable IDs, so an
index alone cannot prove identity after insertions. Map each substantive concept,
definition, nonredundant example, mechanism, condition, comparison and limitation to
a named narration section and eventually its chapter interval. Duplicate source
explanations may share one spoken treatment; record which locators were consolidated
and why no distinct teaching was lost. Inspect all block types,
including formulas and diagram frames. A concept being named is not evidence that
it has been explained. COVERAGE.md should expose both missing source concepts and
scripted sections that still lack verified audio.

## Change detection and receipts

Compute fingerprints programmatically using SHA-256, not timestamps, filename
matches, rounded durations or model-invented hashes. For structured fingerprints,
serialize UTF-8 JSON with sorted object keys, no insignificant spaces and preserved
array order. For scripts and audio files, hash their exact bytes.

plan.json records schema_version=1, course_key, the exact content-file hash, current
category order, each category's key/stem/title, ordered unit keys, semantic input
hashes, source versions, coverage targets and pending actions. It is desired state,
not a completion receipt. Update it without replacing unrelated category records.

Semantic unit fingerprints cover title, summary, objectives, explanations,
formulas/symbols/conditions, table content, literal code and its explanation,
diagram labels/edges/frame states/captions, cards and question answers/feedback.
Exclude source locators/hashes, estimated minutes, navigation labels/paths and
pure diagram layout fields (x, y, shape). Retain ordered content and stable item
keys. Category fingerprints cover its spoken title, ordered unit keys and their
semantic hashes. This separates meaningful teaching changes from formatting,
source-metadata and playlist-only changes. Source references still require review
when their versions change; reuse audio only when the prepared meaning is unchanged.

manifest.json records schema_version=1 and course_key, plus the last published
receipt for each category: key/stem/title, ordered unit semantic hashes, category
hash, source references, script/track/chapter paths and SHA-256 values, actual voice
profile, chunk input hashes, duration and validation evidence paths. Coverage
entries identify the source concept and narration section/chapter. Store only
checks actually performed, including the teaching-review evidence path. That review
records the exact script hash and the SHA-256 of references/narration.md used for
its assessment. Recheck input/script/voice and review fingerprints before promotion
so a concurrent edit cannot be certified against an older snapshot.

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

When no manifest exists, inventory legacy tracks and scripts, including nested
audio packages. Their presence is not proof of current coverage or provider
identity. Adopt a category only after matching its script to current prepared
content and checking its audio; otherwise preserve it as unverified. Migrate legacy
layout only within the requested scope, keeping originals recoverable under audio/.

## Generation, validation and publication

Write work under .build/<run-id>/ and retain a pending record for interrupted runs.
Cache a chunk by its exact spoken text plus provider, model, voice, language, rate,
pronunciation rules and any context/stitching settings that affect its audio.
Changing any of those inputs invalidates reuse. Split at sentences or paragraphs
within the provider's observed limits. Keep an ordered chunk list; never assume a
large partial download contains the final sentence.

Complete the [teaching check](narration.md#teaching-check-before-synthesis) before
synthesis. Keep a concise .build/<run-id>/teaching-review.md with category IDs,
source/script/guidance hashes, objective/concept mapping, consolidation decisions,
word counts, estimated duration and any failed checks and repairs. Reuse existing
coverage records instead of duplicating the full source in this review. Write
"not applicable" for checks with no relevant source material; never invent recall
prompts or a numerical learning score to fill a checklist. Fix clear in-scope
problems yourself, rechecking affected teaching before generation. Do not require
a separate user approval of ordinary scripts or generated candidates.

For a new voice/profile, use the short passage test in the voice guidance before
full synthesis. For an established profile, reuse applicable voice evidence and
test changed technical pronunciations or synthesis behavior when needed. Keep
editorial improvement separate from source changes: changed guidance triggers a
script review, not automatic resynthesis of unchanged, satisfactory speech.

Validate each generated chunk's beginning/end against its expected text; a decode
or plausible duration does not establish full narration. Where transcription is
available and authorized, compare it with the expected text, allowing spelling
differences but investigating missing explanations, numbers, negations and technical
terms. Keep QA and any transcripts under .build/. Use available listening tools for
pronunciation, joins, pace and listening fatigue; distinguish signal checks from
listening checks.

Export AAC M4A, normally mono at 44.1 kHz and about 128 kb/s, normalized near
-16 LUFS with true peak at or below -1.5 dBTP. Tag title, album, track number and
actual synthetic narrator. Use ffmpeg/ffprobe when available; report missing tools
instead of labelling another format as M4A. Derive chapter timings from measured
assembled segments, including deliberate pauses; estimates are not verified cues.

Check the affected files for valid decoding/codec, nonzero and plausible duration,
complete ordered speech, pronunciation of difficult terms, unintended long silence,
chapter bounds, metadata and resolvable playlist paths. An intentional recall pause
is not accidental silence. Verify that every current category is represented and
that any remaining unverified material is visible in COVERAGE.md.

Before publishing, compare the current files with their previous receipt to detect
concurrent/manual edits. Archive the affected old script, track, chapters and
receipt under archive/<UTC-date-time>-<run-id>/. Stage all new category files before
replacement and retain recovery data if a multi-file write fails. Publish verified
category receipts only after the corresponding files are installed successfully;
update manifest.json last via atomic replacement. Then update playlist/coverage and
README from the verified receipts, including unchanged categories. A failed build
keeps the previous usable files and pending work; never overwrite them with empty
or unverified output. Do not delete useful resumable chunks on failure.

Report complete only when the requested current categories have verified coverage.
Otherwise list the completed/reused categories and precise pending material or
provider limitation, with the prepared scripts and recovery path.
