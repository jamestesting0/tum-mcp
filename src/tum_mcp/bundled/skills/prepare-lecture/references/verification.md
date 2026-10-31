# Review notes and highlights

Before building, compare the authored notes and highlights with the full retained
topic map. Review each Note/Highlight/Omit decision: useful addition, suitable
representation, sufficient context and verified content. For each note, check the
claim and its conditions against the speech; preserve explicit instruction scope.
For each highlight, check its timed source, qualifications and supporting material.
Review each thumbnail's actual capture time and visible image; verify names/formulas
against shown material where recognition was unreliable. Keep unresolved gaps visible
in coverage and the private review map. Do not claim complete highlights merely
because every audio chunk ran.

Run `tum-mcp lecture check PROJECT`. It must report no errors. Review `note_items`
against the note text and review every `uncertain_speech` warning. Confirm that each
highlight's opening and closing speech matches its title, teaches line and points.
Inspect the full selected
explanation too: endpoint excerpts alone do not verify its intermediate working.
Confirm the range includes its question/setup and final correction or conclusion.
Check the reported watching time:
reconsider passages that a short note or the materials already explain, without
imposing a fixed count or percentage.

Run one coherent build with `tum-mcp study build PROJECT --local-only`, then
`study inspect PROJECT`. Resolve stale source hashes, wrong course bindings,
missing assets or customized-template conflicts without overwriting user work.
Keep prior usable notes and highlights intact if a source cannot be refreshed.

Open the real app locally (`tum-mcp study` in the project folder). Follow the
Lecture list, a lecture and a highlight deep link. Check:

- The list row shows the lecture's highlight count and watching time; the summary
  states the lecture's scope; note counts and highlight watching time are distinct.
  Notes precede highlights; absent sections leave no empty heading. Notes-only,
  highlights-only and no selected additions must not create dummy cards.
- Notes are concise and self-contained, with no prominent time range or mandatory
  thumbnail. Their source controls open the supporting moment and applicable pages.
  Meaningful images have descriptive alternative text; formulas render correctly.
- Time ranges use the original recording clock. Independently open at least two
  highlight links in the player and confirm that each lands where its explanation
  starts. Do not infer seek behavior solely from the URL. A missing/unavailable player
  is a verification limitation.
- Every thumbnail loads, shows the highlight's topic and lies inside its range.
- Slide or script pages appear in a highlight's sources only where they apply.
- Notes and highlights read well at phone and desktop widths, with no overflowing
  thumbnails, formulas or text and no visible provenance labels. Source/attribution
  review stays private; app behavior itself is covered by the package's tests.
- Selection comments on both notes and highlights save and locate the exact passage.
  A note deep link focuses its item; a highlight deep link focuses its heading.
  Test a stale/ambiguous quote as unavailable; never attach it to a guessed substitute.
  Filter feedback with `study comments list PROJECT --view lectures --lecture KEY`.
- Hosted export disables comments, fetches no campus content/model API and carries
  only explicitly selected workspaces/assets. Lecture publication defaults false,
  including old saved publications. Use publish-course with an explicit
  `--include-lectures` decision; `--exclude-lectures` removes managed lecture images
  from subsequent eligible exports. An excluded Lecture-only export is refused.

A targeted edit needs targeted source/browser checks. Do not repeatedly acquire
unchanged media, re-run inference or rebuild after every highlight. Report what
was prepared/reused, invalid and partial (each failed span's `failures` entry
names its stage and reason; rerunning `lecture prepare` reuses verified media and
chunks and retries only what failed), the remaining coverage/material gaps,
actual validation and publication state. Synthetic demo success tests the product
workflow; it does not establish real lecture accuracy or educational benefit.
