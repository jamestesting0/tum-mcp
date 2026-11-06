# Draft, check, then the review loop

Shared by prepare-study, prepare-exercises, prepare-exams and prepare-lecture. Authoring
(Phase A) ends with a draft that passes every code check; the review loop (Phase B,
review-course) has fresh checkers read it. The session that wrote an item never scores it.

## Phase A: draft and check

1. **Fix the scope once.** From the request, the coverage ledger
   (`tum-mcp study report PROJECT --section coverage`) and `tum-mcp study schedule PROJECT`
   ("this week" and what has been taught). Bonus problems are out unless the student asks
   for them; prepared ones stay and are reviewed. Material released while you work waits
   for the next round of work.
2. **Read each source once into a digest.** `.tum-mcp/digests/<source>.json` holds its
   stated outcomes, worked examples, definitions and figures with their pages, and the
   source's `sha256` from `.tum-mcp/state.json`. `tum-mcp study digests PROJECT` lists
   missing and stale ones. Plans, authors and checkers read the digest instead of the
   whole source; open the source pages for anything the digest does not settle.
3. **Plan every item.** `.tum-mcp/plans/<item>.json` (for example `plans/study/dfs.json`)
   names the item's outcomes and each concept with its `kind` (definition, fact, rule,
   procedure, algorithm, model, comparison), the worked `instance` that shows it and the
   block keys that will teach it; an exercise plan names each `part` with its `answer` and
   `method`. A kind brings a default shape (an algorithm is stepped through, a comparison is
   a table); give `skip` with the reason when it does not fit. Read
   `tum-mcp review checklist --profile PROFILE` first: author and checker read the same
   checks, and the study-unit checklist points to a gate-passing exemplar with its plan and
   answer key.
4. **Pass the plan gate.** `tum-mcp review plans PROJECT` gives the plans waiting for a
   check, and one fresh session reads them: `tum-mcp review run-checker PROJECT --plans`
   (a headless host session, recorded as fresh), or a subagent whose answer you record with
   `tum-mcp review plan-record PROJECT --file ANSWER --provenance fresh`. Checking your own
   plans records them as provisional. A changed plan needs a new check. Rework a rejected
   plan before writing.
5. **Solve first.** For anything computed (a trace, a result, a mock question), write the
   answer key `.tum-mcp/checks/<item>.py` before the item: it prints
   `{"values": {path: value}, "walkthroughs": {block: [state per step]}}` and
   `tum-mcp study verify PROJECT` compares it with the content on every check.
6. **Write each item, then lint it.** Edit the item's own file under `app/` with your edit
   tools (no scripts that rewrite whole workspaces). After each item run
   `tum-mcp study lint PROJECT --item ITEM`: schema, report flags, the plan's links and the
   answer key in seconds. Fix every invariant flag; read every other flag and fix it or
   keep it for a stated reason. Text-only questions are invariant defects; even a
   checker's waiver cannot clear them. The flags marked for a ruling (inline lists,
   a shorter definition than the course's, a lesson without a visual) are ruled on
   again by the checkers, and the gate holds until each has a ruling.
7. **Check the batch.** `tum-mcp study build PROJECT`, `tum-mcp study visuals PROJECT`
   (desktop; fix every render defect in the content) and
   `tum-mcp study visuals PROJECT --interact` (every stepper, Guide | Solution pill and the
   search must respond). Contact sheets cover drawings and tables, not formulas,
   derivations or code. Open affected excluded blocks in the built app, including
   revealed answers; inspect clipping and readability at the requested widths.
8. **Ask.** Show what was drafted and the estimated first-round workload, then ask:
   "Run the review loop? Budget: 5 rounds." Ask in the student's terms; do not cite skill
   files or workflow names. Skip the question when the request already asks for a review,
   and do not ask again in the same session once the student has answered.

## Phase B: the review loop

review-course drives `tum-mcp review`: fresh checkers read packets, the maker fixes by
check, code re-runs the checks above, and the gate passes when correctness and coverage are
3, every teaching check passes and the rest are at least 2 with a kept reason. Publishing
reads the same gate.
