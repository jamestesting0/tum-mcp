---
name: review-course
description: Run the review loop on prepared Study, Exercises, Exam, Lecture content and course structure - fresh checkers read packets, the maker fixes by check, code re-checks, and the gate decides. Also reviews audio and video against their sources, frames and machine listening (listen); media scores stay separate.
---

When `tum-mcp study status PROJECT` reports `course_memory: true`, use
the installed `course-memory` skill for relationships and scoped source updates.
When disabled, leave retained graph files unused and follow the ordinary workflow.

Work in the course project bound by AGENTS.md and `.tum-mcp/state.json`. Content lives in
one file per item under `app/` (`app/study/units/`, `app/exercises/<set>/`, `app/exam/`,
`app/lectures/`). `tum-mcp review` keeps the loop's state, packets and verdicts in
`.tum-mcp/`; you never write review files by hand.

A judge favours its own work. Checkers are fresh sessions that did not write the content
and do not share this conversation: host subagents that start empty, otherwise
`tum-mcp review run-checker PROJECT --packet ID` (or `--plans` for the plan gate; a
headless installed host, read-only). A subagent that inherits this session's context (a
forked Codex agent) is not fresh: use run-checker there. With neither, record with `--provenance same`: the
result stays provisional and cannot pass the gate. The authoring session fixes; it never
scores.

## The loop

1. **Start.** Phase A of the [draft checks](../prepare-study/references/loop.md) is done
   (lint, verify, visuals and `--interact` clean). `tum-mcp review start PROJECT` fixes
   the scope and defaults to one round. For prepared Study or Exercises, use
   `tum-mcp review start PROJECT --preparation ID` after the readiness report passes.
   For any declared batch matching the request, including one workspace, use
   `review start PROJECT --batch ID` after
   `study report PROJECT --section readiness --batch ID` passes. This binds the
   complete declared request, its preparation scopes, Exam drafts and recording
   selections to one round. To review several prepared batches together, declare one batch
   that lists their items and preparations; their approved plans stay approved.
   For ad hoc reviews use `--workspace` to narrow the scope.
   A declared unfinished batch requires its batch gate. Use `--ad-hoc` only for an
   explicitly partial review. A later loop asks about new and changed items.
   A filtered review that exactly matches one ready batch retains that batch's source
   requirements automatically. A subset remains partial; do not call it a full review.
   A verdict holds until the blocks it covered change.
   For a registered batch, retain its task until the approved round and repairs end.
   When review is newly approved after a draft-only handoff, register that batch with
   `study task start PROJECT --batch ID --review-rounds N` using the authorized budget.
2. **Each round.**
   1. `tum-mcp review next PROJECT` writes bounded packets per profile under
      `.tum-mcp/review/packets/`. Each holds its checks with a pass and a fail example,
      the items with their passages and block ids, the report flags, the answer key's
      result, the digests of the cited sources, the findings to verify and the findings
      already rejected with their reasons. An oversized item is split into batches of
      checks, visuals, fixes and rulings. Each retains the full passages, outline, sources
      and captures; every batch must be recorded before its scores are current.
      The weakness is partial review presented as complete. Splitting a packet changes
      its workload, not its context or the checks required for a pass.
      For items that need visual scores,
      `visual_sheets` links the available captures of the current
      draft. Use those images when scoring the six visual criteria.
      Desktop is the check; use `--phone` only when the student asks.
   2. Give each packet to a fresh checker as its whole brief. When the host supports
      concurrent checker sessions, start independent packets together and leave the draft
      unchanged until all answers are recorded. The checker answers in the packet's
      format after its headless command finishes. A quiet command with a live session
      handle is still running: wait on that same handle until completion or the actual
      host timeout. Do not cancel it, duplicate its packet request, or close the round
      incomplete merely because it has not printed progress. A duplicate request is
      refused while the first checker holds that packet; other packets remain independent.
      The checker uses the packet's
      `answer` format: a verdict (`pass`, `fail` or `uncertain`) for every check with the
      blocks it read, and for each fail the quoted passage, why it fails and the fix.
      Uncertain needs a `missing` field naming the specific artifact or source page
      that cannot be opened and why. Incomplete sampling is not unavailable evidence.
      A sampled check whose likeliest failures pass is a pass.
      The weakness is confusing a review limit with a content defect. Name unavailable
      evidence precisely; do not infer failure from silence or pass an unread check.
      Checkers look at cited source pages for logic checks as well as the digest.
      Reuse matching page images under `.tum-mcp/cache/pages/<sha256>/` in read-only
      sessions. The author can render a missing cited page with
      `tum-mcp study text PROJECT --key K --pages N --images`. Every report flag marked
      `needs_ruling` gets a ruling in `flags`: a finding about it, or `not_applicable` with why; the gate
      holds until each has one. `intuition.concepts_instanced` is answered concept by
      concept from the packet's `concepts`. A finding is resolved only with the rewritten
      passage quoted, and only when that passage reads well on its own.
      Also inspect concepts added after planning; adding a glossary paragraph to justify
      new flashcards does not teach those concepts. For objectives, cite the actual
      source outcome or developed explanation, not an illustrative aside.
   3. `tum-mcp review record PROJECT --file ANSWER --provenance fresh`. It refuses answers
      for content that changed since the packet, unknown blocks and unquoted passages.
   4. Group findings that share a cause and make one coherent repair. Rewrite the whole
      passage a finding sits in, never splice a sentence
      ([writing](../prepare-study/references/writing.md#fix-the-passage-not-the-sentence)).
      Edit the item files, then `tum-mcp review fix PROJECT --item ITEM --finding F`
      (refused while the quoted passage is unchanged; name `--block` when you fixed it
      elsewhere). A finding that is wrong: `review reject` with the reason the content is
      right; the next checker sees it. A retry with the same owner, location and quote
      keeps the existing open or fixed finding even when its wording changes.
      A score-2 finding the content cannot fix (the
      source gives no smaller example): `review keep` with the reason.
   5. Check changed claims and citations against the named source pages; matching source
      hashes do not establish that a page supports a new claim. Lint changed items with
      `tum-mcp study lint PROJECT --item ITEM`. After the repair
      batch, rebuild once and recheck the affected visuals and interactions. Inspect the
      changed rendering, including any formulas or code outside the contact sheets.
      A finding may require splitting an item. Keep the original key for one part, create
      the other complete items, update their plans, source-demand targets and the batch
      item list, and fix links/paper assignments. Check only changed or new plans. After
      all original packets are recorded and the entire batch is ready, run
      `review repair-scope PROJECT --reason REASON`. This permits additions in the same
      workspaces while preserving the original request, sources and required demands;
      it cannot remove reviewed items or reset the budget. Do not keep a repairable
      structural finding merely because it needs another item. Mark the original finding
      fixed after its passage changes. Added items receive no copied scores or extra
      automatic review; report them as awaiting independent verification.
      Repair can also finish after the round has closed: it updates the current
      scorecard without opening another round. New corroborating sources are permitted
      while the original source revisions, request and required demands stay fixed.
   6. Finish every original finding and draft repair before running
      `tum-mcp review verify PROJECT` in the open round. Give its packets to fresh
      checkers and record every batch. Read every changed block against its cited source
      pages and the reference selection. A finding demanding another worked example
      must name the missing understanding or decision the existing examples cannot show;
      otherwise it is not a defect. The weakness is repetition added without a teaching
      purpose. A distinct source demonstration or needed boundary case can still be essential.
      Repair only findings this pass opened, then run `review verify PROJECT` again.
      This second pass asks all stale checks, visuals, fixes and rulings only for items
      changed since the first pass. Record its fresh answers, then close. There are at
      most two verify passes per round. Report repairs after the second as unverified;
      another check needs another round requested by the student.
   7. `tum-mcp review close-round PROJECT` computes the gate and writes
      `.tum-mcp/loop/scorecard.md`. Use `review status` to check progress while a
      round is open. If a packet cannot be recorded, finish the available repairs
      before deliberately closing with `--incomplete` and report the missing review.
3. **Stop** when the gate passes, when the budget is spent, or when the student stops. A
   spent budget lists the findings, fixes, review provenance and what still needs
   verification. Use `tum-mcp review extend PROJECT` if the student requests another round. `uncertain` verdicts go to the student under "needs
   your eye"; record their decision with `tum-mcp review resolve`.
4. **Resume** any time with `tum-mcp review status PROJECT`: where the loop stands and the
   one next action.

The gate passes an item when correctness and coverage score 3, every teaching check
passes and every other dimension is at least 2 with a kept reason. An open invariant flag
(an answer key that disagrees, arithmetic, typed mathematics, a static trace, an unworked
result, text-only question, a cited page past the source's end, a listed paper students cannot practise) holds
its dimension below 3 until fixed. Sources no exam requirement records yet hold the course,
shown as `course` in the scorecard, not the item they are filed under: a scoped section can
pass while the course stays open, and publishing waits for both. A spent budget with fixes
made after their last check says so; `review extend PROJECT --rounds 1` verifies them.
Missing question context holds the gate even if a checker waives its flag. Reframe the
question around a useful object or case; a decorative picture does not fix it.

Repair gotchas:
- The weakness is a detached repair. Repair inside the section the finding sits in;
  a course dependency may instead need a linked repair in its earlier home.
- The weakness is a representation chosen by habit. Show the object and the changes
  that explain the idea. Keep tables for comparisons and lookup, and a static picture
  when its structure is the point; do not force every subject into a walkthrough.
- The weakness is lost teaching during cleanup. Remove content only when it is wrong
  or said twice. Preserve each selected example's inputs, representation, decisive
  working, endpoint and the comparison or result that explains its point through repairs.
  A useful continuation beyond the lecture is fine; covering less is not. Do not add a
  comparison the example does not need. Keep distinct examples that teach different decisions.
- The weakness is fitting the viewport by shrinking the lesson. Never cut teaching to
  close an unrelated finding or fit an unrequested width. Judge scrolling by legibility
  at the requested desktop width; preserve the full source example.

## What each profile reads

`tum-mcp review checklist --profile PROFILE` prints the checks of one kind of item. Read
the [workspace profiles](references/profiles.md) for what an exercise, an exam pattern, the
cheatsheet, a mock question or a lecture entry is for: an exercise guide is not a second
Study lesson. The course item reads the structure map as in [course](references/course.md).
Visual criteria and the improvement loop are in [visuals](references/visuals.md); score a
few cases of the [visual gallery](references/visual-gallery.json)
(`tum-mcp study visuals PROJECT --gallery`) and the
[structure gallery](references/structure-gallery.md) before a session's first packet,
when the checker is new to them.

## Media

Audio and video are reviewed against their sources, frames and narration; follow
[media](references/media.md) and its [media pairs](references/media-gallery.md). Run
`tum-mcp audio-notes listen` or `tum-mcp video-notes listen` on each published item for
the listening evidence; fresh checkers read each script against its sources (and the
frames) and score every dimension that evidence supports. Fix what you find (reword a
sentence the recognizer still cannot hear, recompose a slide, restore a missing
condition), publish again, re-listen, have a fresh checker confirm the changed chapters,
and save every reviewed item with its scores; a repaired item is not left unsaved.
Media reviews go to `.tum-mcp/review/media.json`; `tum-mcp study report PROJECT --section
review` shows their status. A dimension with no supporting evidence stays unscored, never
a perfect score, and it never holds back publication. Judge coverage against what the
student asked for (a cheatsheet track covers every entry and pattern).

## Report

After the authorized budget, read `review scorecard PROJECT` and report the review
scores, repairs and remaining issues. Include scored/in-scope counts; an average over
only the unchanged items is not an overall score for the repaired batch.
Run `study task finish PROJECT` for an active registered batch before the report.
Separate independently checked scores from changes still awaiting verification.
A spent round with completed repairs is the authorized handoff, even when its quality
gate awaits another independent check. Report that limitation; it is not an external
blocker requiring task pause. Findings on removed derived entries do not require
inventing replacement content. Do not silently add a review round to clear them.
Offer another round; never extend the budget without the student's request.

Give the gate status and verified/in-scope counts, open findings by check, the
per-workspace rows, items below the bar, findings opened and closed per round, rejected
and kept findings with reasons, "needs your eye" and what changed. Scores describe this
review, not mastery or exam readiness.

## Boundaries

Packets, verdicts, scorecards and contact sheets stay in `.tum-mcp/`; they are never shown
to students or published. Never mark a check passed without reading it, and never lower
the bar to pass. A review does not authorize new sources: fetch missing material through
read-content and record outcome gaps in the coverage ledger instead of guessing.

For units with Explore or changed optional classifications, include the
[core-only counterfactual review](../prepare-study/references/explore.md#review-with-explore-closed).
Optional teaching is part of the unit's accuracy and visual review; it cannot supply core
prerequisites, trace requirements or assessment coverage.
