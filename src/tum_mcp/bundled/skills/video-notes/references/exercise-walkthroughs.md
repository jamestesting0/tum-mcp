# One prepared problem, completely explained

A walkthrough solves the selected Exercise, not its whole topic. Concise means
removing detours, never necessary instruction, intuition or visual demonstrations.
A longer clear solution is better than a short opaque chain of algebra.

## Bind the actual source

Finish and check prepare-exercises first. Read the exact statement, ordered parts,
givens, conventions, solution origin and prerequisites. Run:

```text
tum-mcp video-notes exercise PROJECT SET/KEY
tum-mcp video-notes schema selection
tum-mcp video-notes plan PROJECT --selection FILE
tum-mcp video-notes outline PROJECT STEM
```

Selection entries use `exercises: [{exercise: {set: SET, exercise: KEY},
decision: "video", reason: "..."}]`. `outline` writes the storyboard with the hash
and every locator fingerprint filled in. Exercise storyboards have `exercise`, `exercise_hash`, `answers`;
not a fabricated Study unit or objectives. Locators address `statement[N]`, exact
step keys, `answers[N]`, `notes[N]`, or a declared `unit[/block]` prerequisite.
Only actually used prerequisite meaning belongs in this video.

Chapters carry an `answer` locator (or none for an initial shared setup).
Cover every required answer in original order, including all secondary demands.
Several consecutive chapters may explain one part. Do not infer coverage from
chapter titles or truncate a problem with more than twelve parts. Every statement
part, guide step and answer is presented by a beat or listed in `left_to_page` with
the reason the page serves it better.

## Build the solution

1. **Setup:** establish the actual shared problem before solving any part. Show
   the givens, constraints, conventions and needed diagram/table/code context.
   For each part, state exactly what must be found or proved. The poster shows
   the setup, not the result.
2. **Strategy:** explain why this method fits the givens and requested quantity.
3. **Work:** show meaningful transformations, live state and reasons in order.
   Retain earlier results when reused. Group only routine arithmetic, not the
   inference the exercise tests.
4. **Verify:** independently check domain, signs, units, substitution, residual,
   boundary conditions or the logical claim as applicable.
5. **Answer:** emphasize the requested result after its explanation and check.
   Use a clearly separated answer, an outline/underline or a focused final view,
   including units and conditions. For multiple parts, finish with a compact
   summary that includes every requested result.

Those are the Exercise beat kinds. A proof needs justified implications; a
physical problem needs consistent diagram conventions; an algorithm needs visible
state updates; statistics needs conditioning and interpretation.
`storyboard check` requires setup, strategy, work, verify and answer for each
mapped part, in teaching order. A part may span chapters and several work beats;
the roles do not require five disconnected screens or a fixed number of seconds.

At the conceptual bottleneck, integrate the visual demonstration with the live
calculation: map equation terms to components, show why substitution simplifies
the task, or show why an update preserves an invariant. A diagram beside unrelated
algebra is insufficient. Matching equation parts, restrained highlighting and
measured cues matter more than animating every handwritten stroke.

Show the current operation or inference as it is explained. Do not reveal later
steps or the final result before the relevant narration. Restore context when
moving to another part, rather than relying on a chapter label alone.

Lay the screen out like a worked solution on a board: the problem's model (its
diagram, world or givens) stays in one region for the whole part, the working grows
or transforms in another, and only the current line changes. Cases or alternatives
go in a `self.grid` table whose rows fill in as each case is worked, with
`.highlight(r)` on the row being discussed. Calculations are `math` items that
transform step by step. The answer gets an `emphasis` frame after its check, and a
multi-part problem ends on one summary grid of every requested result.

No stock branding intro, unrelated recap, added example, quiz or mandatory pause-and-solve.
Source defects return to prepare-exercises; missing exposition/timing returns here.

## Exam patterns

A pattern video teaches a method the student reuses on every exam question of its
kind. `tum-mcp video-notes pattern PROJECT KEY` prints its parts. Selection entries
use `patterns: [{pattern: KEY, decision: "video", reason: "..."}]`. The outline has
these stages:

1. **When it applies:** the cues in a question that call for this pattern.
2. **The method:** each workflow step in its own `step` beat, with the formula, rule
   or code it applies on screen. Each case of a decision step gets a `case` beat:
   what the student sees, then the move.
3. **Worked example:** the first example, one `example` beat per workflow step, so the
   student sees each step used.
4. **Pitfalls:** each one as the wrong working, then the right one, and why.
5. **Recap:** the steps in order, with the marking notes and variations.

A further example that shows a new case gets its own chapter; one that repeats a case
goes to `left_to_page` as "repeats case N". Drill items are never shown, since
solving them would spoil the practice. The clip plays on the pattern's Exam page.

## Encounter and review

Single-part clips appear inside the existing Solution; multi-part clips get one
closed “Video solution (all parts)” disclosure. Opening does not autoplay or mark
written parts complete; closing pauses. Exercise clips never appear in Exam.

Test closed/open, sound, captions, chapter seeks and transcript at phone/desktop
widths. Review using the source-derived Exercise profile in
[media review](../../review-course/references/media.md). Do not impose concept
lesson expectations such as a new example or general theorem exposition.
