# Reviewing the artifact the student encounters

Run `tum-mcp study report PROJECT --section review`. `review.media` lists published,
pending, invalid, stale and unreviewed artifacts, code-built revisions, missing
evidence and required dimensions. Audio/video averages are separate from Study.
No media is fine; broken present media blocks the media gate without hiding Study
diagnostics. A successful render, script review or transcript does not certify
perception or learning.

## Evidence and saving

1. Calibrate on [actual paired assets](media-gallery.md). Then read the selected
   prepared source, script and coverage. Review claims, notation, assumptions,
   every Exercise demand and any disclosed Study dependency.
2. Check raw probe/decode/loudness results against the exact artifact, not a
   handwritten `passed` flag. Open all video entry/middle/exit sheets and compare
   actual states/formulas with source and narration.
3. Hear the entire final audio. For video, also watch the entire sequence with
   sound, captions and transitions. Record actual intervals, including re-entry at
   chapters. A playback tool without sound perception supports synchronization
   observations, not delivery. ASR, waveforms and frames do not replace hearing.
4. Save `media` entries beside existing `reviews` and `course` in
   `.tum-mcp/review.json` (`study schema review`). Copy the report's current item
   (`audio/CATEGORY` or `video/STEM`) and revision; never calculate or reuse a
   revision by filename. Preserve unrelated reviews.

Each entry has `item`, `revision`, `reviewed_at`, `scores`, optional `findings`,
`visuals`, `evidence`, and optional `kept`. Each finding owns one dimension/check
and names an interval (`start`, `end`), chapter/beat, or exact source concept
(`study/UNIT#LOCATOR` or `exercises/SET/KEY#LOCATOR`). Use only check IDs below.

Evidence entries contain `kind`, confined relative `path`, actual `sha256`, and
`artifact_sha256` from the report. Use private `.tum-mcp/media-review/`,
`audio/.build/`, `videos/.build/` or `videos/reviews/` paths. Hash actual bytes:
do not write fabricated digests. `script` evidence also has the report's
`guidance_sha256`. `listening` and `playback` carry `intervals: [{start: 0,
end: ...}]` for what was actually perceived. Only `playback` can set
`audio_perceived: true`, when sound really was heard.

Audio needs script, signal and full listening coverage. Video also needs frames,
every listed visual scored on all six visual criteria, and full playback coverage.
Overlapping observations are fine; gaps are incomplete. Unknown visual IDs, profile
checks, locations, changed evidence and out-of-bounds intervals fail. Missing
capability leaves the affected dimensions unscored and the gate incomplete.
Never write a synthetic observer receipt outside a machine-contract test.

## Shared checks

A 3 means checked and easy to follow; 2 means friction; 1 blocks understanding or
misrepresents meaning. One serious defect sets the dimension's score, not an average.

| Dimension | Checks (all prefixed by the dimension) |
| --- | --- |
| correctness | `source_match`: facts and values agree; `conventions`: signs, units, ordering and assumptions survive adaptation. |
| clarity | `spoken_referents`: objects are named before use; `terms_defined`: terminology introduced at use; `no_meta`: no production commentary. |
| cognitive_load | `one_change`: one meaningful update at a time; `external_state`: needed state is visible in video or restored in speech. |
| coverage | `media_mapping`: every substantive assigned concept/demand maps to actual teaching; `dependencies_disclosed`: exact Study-only limits are stated, not hidden. |
| intuition | `reasons`: important moves have reasons; `limits`: applicability and failure conditions are clear. |
| organization | `media_sequence`: dependency order holds; `chapters`: boundaries support orientation and navigation. |
| redundancy | `media_filler`: no stock intro or repeated explanation adding nothing; `caption_exception`: captions may repeat speech for access, not penalized as duplicate teaching. |
| delivery | `intelligible`, `pronunciation`, `complete`, `joins`, `pace`: listen for intelligible technical terms, all words/negations, clean joins and time to understand. |
| representation (video) | `fidelity`, `form`, `layout`, `legibility`, `focus`, `convention`: apply the six visual criteria; `shown_not_described`: show actual objects; `state_fidelity`: every intermediate state is valid. |
| synchronization (video) | `referent`: speech points to the current object; `captions`: timed and correct; `reveal`: reasoning and result appear at the right moment. |

Audio has the first eight dimensions. Video has all ten. Neither has Practice:
ordinary listening or viewing needs no invented interactive question.

## Source-derived profiles

The report selects the profile from the actual source receipt, not a label supplied
by the reviewer. Do not impose concept-lesson shape on a worked solution.

**Audio revision**, additional checks:
`clarity.audio_independence` (no unseen “this”); `organization.audio_rejoin`
(chapter starts restore subject/referents); `intuition.revision_decision`
(distinguish confusable rules and their use); `redundancy.useful_reinforcement`
(keep orientation and useful contrast); `delivery.condition_emphasis` (negations,
exceptions and conditions are audible). Test the full track hands-free and directly
enter first/middle/last noninitial chapters. Study-required construction is a
disclosed limit, not proof of audio-only completeness.

**Concept video**, additional checks:
`intuition.visual_construction` (visible reasoning establishes why);
`representation.correspondence` (objects map to symbols/quantities);
`organization.visual_thread` (stable objects carry the argument);
`cognitive_load.reorientation` (return from close-up to whole);
`redundancy.complementary_explanations` (a second view adds understanding);
`organization.lesson_overview` (the opening establishes the learning question,
scope and section map); `organization.knowledge_points` (sections develop their
named points rather than skipping from label to label);
`organization.lesson_closure` (the ending connects the results and resolves the
opening question).
With Video Notes installed, use its `references/explanation-design.md` mechanism
families: transformations, limits, signals, probability, state, space, proof and
representation changes.
Correct final formulas with missing/invalid visible reasoning score 1 when the
central mechanism is lost. Duration is not a failure.

**Exercise video**, additional checks:
`correctness.statement_fidelity`, `coverage.exercise_demands`,
`intuition.method_choice`, `intuition.local_mechanism`,
`representation.working_shown`, `representation.problem_correspondence`,
`correctness.result_verified`, `redundancy.exercise_scope`,
`synchronization.step_reveal`, `organization.exercise_setup`,
`representation.answer_emphasis`. These mean: preserve the exact problem and origin;
answer all parts and secondary demands; justify this route and its bottleneck;
show transformations and their meaning; independently verify the result; avoid
unrelated theory; align each step with speech. No compulsory extra example, theorem
exposition or prediction. Longer and clear beats shorter and opaque.
Establish the actual givens, conventions and requested parts before solving.
Keep the current reasoning visible and emphasize each final result after its
explanation and verification. A complete multi-part answer summary should not
require the student to reconstruct results from scattered frames.

## Repair and completion

Fix source meaning in prepare-study/prepare-exercises. Fix adaptation, scenes,
pronunciation or timing in audio-notes/video-notes. Rebuild only affected material,
then re-read/hear/watch the changed artifact and save fresh observations. Byte,
source, voice, style, asset or guidance changes stale relevant reviews.

A 1 is never kept. Keep a 2 only for a concrete source/modality limit that cannot
be fixed within scope, with that limit disclosed to the student. `kept` never
waives readiness, evidence, missing dimensions or stale inputs. Useful reminders,
captions and alternative access to Study are not needless course duplication.
Use media links and chapter/coverage structure in the course pass; codec bytes do
not change its outline revision.
