---
name: review-course
description: Run the review loop on prepared Study, Exercises, Exam, Lecture content and course structure - fresh checkers read packets, the maker fixes by check, code re-checks, and the gate decides. Also reviews audio and video with real listening and playback; media scores stay separate.
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
   (lint, verify, visuals and `--interact` clean). `tum-mcp review start PROJECT
   --rounds 5` fixes the scope (add `--workspace` to narrow it). A later loop asks only
   about new and changed items: a verdict holds until the blocks it covered change.
2. **Each round.**
   1. `tum-mcp review next PROJECT` writes one packet per profile under
      `.tum-mcp/review/packets/`. Each holds its checks with a pass and a fail example,
      the items with their passages and block ids, the report flags, the answer key's
      result, the digests of the cited sources, the findings to verify and the findings
      already rejected with their reasons.
   2. Give each packet to a fresh checker as its whole brief; it answers in the packet's
      `answer` format: a verdict (`pass`, `fail` or `uncertain`) for every check with the
      blocks it read, and for each fail the quoted passage, why it fails and the fix.
      Checkers look at the cited source pages for logic checks (`tum-mcp study text --key K
      --pages N --images`), not only the digest. Every report flag marked `needs_ruling`
      gets a ruling in `flags`: a finding about it, or `not_applicable` with why; the gate
      holds until each has one. `intuition.concepts_instanced` is answered concept by
      concept from the packet's `concepts`. A finding is resolved only with the rewritten
      passage quoted, and only when that passage reads well on its own.
      Also inspect concepts added after planning; adding a glossary paragraph to justify
      new flashcards does not teach those concepts. For objectives, cite the actual
      source outcome or developed explanation, not an illustrative aside.
   3. `tum-mcp review record PROJECT --file ANSWER --provenance fresh`. It refuses answers
      for content that changed since the packet, unknown blocks and unquoted passages.
   4. Fix by check, not item by item: the same check failing in several items has one
      cause. Rewrite the whole passage a finding sits in, never splice a sentence
      ([writing](../prepare-study/references/writing.md#fix-the-passage-not-the-sentence)).
      Edit the item files, then `tum-mcp review fix PROJECT --item ITEM --finding F`
      (refused while the quoted passage is unchanged; name `--block` when you fixed it
      elsewhere). A finding that is wrong: `review reject` with the reason the content is
      right; the next checker sees it. A score-2 finding the content cannot fix (the
      source gives no smaller example): `review keep` with the reason.
   5. Re-run the code checks on what changed: `tum-mcp study lint PROJECT --item ITEM`,
      `study build`, `study visuals` (`--unit`, `--exercise`, `--exam`) and `--interact`.
   6. `tum-mcp review close-round PROJECT` computes the gate and writes
      `.tum-mcp/loop/scorecard.md`.
3. **Stop** when the gate passes, when the budget is spent, or when the student stops. A
   spent budget lists the open findings and asks whether to go on
   (`tum-mcp review extend PROJECT`). `uncertain` verdicts go to the student under "needs
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

Audio and video are reviewed with actual listening and playback, never from the script
alone; follow [media](references/media.md) and its [media pairs](references/media-gallery.md).
Media reviews go to `.tum-mcp/review/media.json`; `tum-mcp study report PROJECT --section
review` shows their status. Missing perception is an incomplete review, never a perfect
score.

## Report

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
