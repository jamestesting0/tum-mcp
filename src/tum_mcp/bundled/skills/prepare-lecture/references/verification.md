# Review the actual notes

Before building, compare the authored sections with the full retained topic map.
For each consequential statement, check its timed source, qualifications and
supporting material. Review each included capture's actual time/visible image;
verify names/formulas against shown material where recognition was unreliable.
Keep unresolved gaps visible in coverage and the private review map. Do not claim
complete notes merely because every audio chunk ran.

Run one coherent build with `tum-mcp study build PROJECT --local-only`, then
`study inspect PROJECT`. Resolve stale source hashes, wrong course bindings,
missing assets or customized-template conflicts without overwriting user work.
Keep prior usable notes intact if a source cannot be refreshed.

Open the real app locally (`tum-mcp study` in the project folder). Follow the
Lecture list, a lecture and a section deep link. Check:

- Overview and takeaways help the student revisit the lecture; sections explain
  useful reasoning beyond the materials without duplicating a Study chapter.
- Timestamp/range links use the original recording clock; independently open a
  selected destination and confirm the expected point. Do not infer seek behavior
  solely from the URL. A missing/unavailable player is a verification limitation.
- Every chosen image loads, enlarges by keyboard and retains legible symbols,
  caption, alt text and a sources link to its actual capture time. No need for a
  frame quota.
- The changed notes read well at phone and desktop widths, with no overflowing
  figures, formulas or tables and no visible provenance labels. Source/attribution
  review stays private; app behavior itself is covered by the package's tests.
- Selection comments save and locate the exact passage. Test a stale/ambiguous
  quote as unavailable; never attach it to a guessed substitute. Filter feedback
  with `study comments list PROJECT --view lectures --lecture KEY`.
- Hosted export disables comments, fetches no campus content/model API and carries
  only explicitly selected workspaces/assets. Lecture publication defaults false,
  including old saved publications. Use publish-course with an explicit
  `--include-lectures` decision; `--exclude-lectures` removes managed figures from
  subsequent eligible exports. An empty excluded notes-only export is refused.

A targeted edit needs targeted source/browser checks. Do not repeatedly acquire
unchanged media, re-run inference or rebuild after every paragraph. Report what
was prepared/reused, invalid and partial, the remaining coverage/material gaps,
actual validation and publication state. Synthetic demo success tests the product
workflow; it does not establish real lecture accuracy or educational benefit.
