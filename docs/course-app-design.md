# Course app design contract

## 1. Atmosphere and identity

Preserve the Study overview in the supplied screenshots: quiet navy or white
canvas, readable Atkinson typography, divided rows and restrained blue feedback.
This contract covers the shared overview rows, Exercises sheet disclosures and
Exam information;
the existing course-app tokens continue to govern the rest of the interface.

## 2. Color

Use the existing stylesheet tokens, with light / dark values:

| Role | Token | Light | Dark |
| --- | --- | --- | --- |
| Canvas | `--canvas` | #ffffff | #101a28 |
| Subtle surface | `--surface` | #f7f9fb | #152236 |
| Primary text | `--ink` | #072140 | #e9eef5 |
| Secondary text | `--muted` | #526477 | #aabbd0 |
| Neutral divider | `--line` | #d8e1e9 | #344253 |
| Active text and focus | `--accent` | #3070b3 | #8cbffa |
| Hover and press wash | `--wash` | #eaf2fa | #203b55 |

No new palette, decorative stripes, shadows or accent card outlines.

## 3. Typography

Keep `--font-ui`: Atkinson Hyperlegible Next, Avenir Next, Segoe UI, system-ui,
sans-serif. Overview titles use `--text-body` (18px), weight 500, line-height 1.45.
Metadata uses `--text-small` (14px), weight 400. Pending source names use
`--text-ui` (15px). Existing page headings remain unchanged.

## 4. Spacing and layout

Reuse the 4px scale: `--s1/2/3/4/5/6/8/12/16` =
4/8/12/16/20/24/32/48/64px. Overview rows use 12px vertical and horizontal
padding, a 4px copy gap and 16px between title and status. Neutral 1px rules
separate rows. Keep the existing reading column and scroll ownership.
Sheet metadata wraps beneath its title; the chevron stays at the trailing edge.
Unprepared sheets follow prepared sheets, separated by 32px, on a subtle surface
with the existing 6px radius. Their list remains in normal page flow.
Content spacing is set by relation, not per component: a block starts flush with its
body, and the container places what follows. Heading to its content `--space-heading`
(12px), prompt or caption to its context and context to options `--space-related`
(16px), block to block `--space-block` (16px), sibling groups `--space-between` (24px),
sections `--space-section` (48px). The spacing browser test measures these relations on
Study, practice, guide, solution, pattern, mock and lecture routes.
Layout: exercise parts use the existing reading stack: shared context, then each
part's statement and supporting blocks followed by its Guide | Solution pill and the one
panel it opens; scroll owner remains main on desktop and the document on phones. The
open panel occupies the full reading width. Never collect all guides or answers after
all parts.

## 5. Components and states

- Explore is a fourth Study tab only for units with nonempty authored optional material.
  Keep the Content/Flashcards/Practice sequence and core progress unchanged. Open
  directly on the reading without an “Optional” label or introductory banner.
  Render item headings and blocks with existing reading primitives, sources
  and spacing; no new palette, frames, banners, decorative icons or animation.
  Optional item headings use `--text-section`; inner blocks use the existing nested
  heading scale. Each item is separated by `--s8`. No optional video/player.
  Below 600px, four-tab units hide visible card/question count suffixes while keeping
  them in accessible labels and activity headers; three-tab units remain unchanged.
  Retain 44px targets, native wrapping at extreme widths, roving keyboard focus and
  current wash/focus treatment. Missing optional targets show a concise notice and
  available material; units without Explore return to Content. The only automatic
  bottom action in Explore is “Back to Content”.
- Optional backlog and unknown coverage stay in agent reports. The learner overview
  shows only known core preparation gaps. Pending work never creates an empty Explore tab.

- Topic row: semantic list item with one full-width link, title and metadata, optional trailing
  progress. The link contains the entire row, including the
  status. Hover anywhere paints the whole row with `--wash`; keyboard focus uses
  the same wash and the existing visible focus ring. No click-handler imitation.
  Lecture is a sibling consumer of this primitive.
- Exercise sheet: native details/summary, with a title and problem-count/week/due
  metadata using the topic row's type and padding. A trailing chevron indicates
  expansion. Default first-sheet expansion and sidebar behavior remain intact.
  Children keep their real exercise links, with inset spacing distinguishing them
  from the sheet header. Hover/focus use the full summary area.
- Exercise help: each part has one segmented pill, **Guide | Solution**, after its full
  statement and supporting blocks, and one shared panel below it. Choosing a segment
  swaps the panel in place; choosing the open segment again closes it. The segments are
  toggle buttons (`aria-pressed`), the chosen one filled with `--accent`; arrow keys keep
  paging the open guide. The open
  segment is remembered per part. A place with only a Solution (mock questions, pattern
  drills) shows the single segment as a toggle. Reading the question is primary;
  guidance and the direct answer are optional peers, with no completion prerequisite.
  Each Solution reveals only its part's answer, without a repeated part heading. Keep
  every answer, source link, review anchor and shared solution note. Shared notes appear
  once after the questions, as do optional transfer tasks. Guide steps and solution
  headings stay out of Contents. Opening or closing one part's panel must not alter
  another part or the guide's progress.
- Example: a worked case read whole, on `--surface` with the existing radius: a small
  muted "Example" label, the givens as a list, numbered steps in the Study step style and
  the result in semibold. No heading of its own; a titled block names it in the outline.
- Callout: a pitfall uses the Exam pattern pitfall item (situation, wrong and right move
  with their marks, why) under a muted "Pitfall" label; a note is one or two sentences
  beside a 3px `--line` rule. At most one per section; no icon, colour wash or banner.
- Lecture note: a muted kind label (Clarification, Example, Exam tip, Intuition,
  Correction), the title with its sources, the situation, the message, then the working
  as numbered steps and consequences as points, an optional figure or frame, and a
  footer with "Watch mm:ss" and Recall. The recording time appears only in the footer.
- Walkthrough: a stage (graph, table, code, working, plot or figure) on top, the step
  card below it (eyebrow "Step N of M · subgoal", the action in bold, the reason, an
  optional pitfall on `--warning`, the variant contrast on `--wash`, then the state rows
  with changed values marked), then the controls: previous, step dots grouped by
  subgoal with a thin rule between groups, next, and "All steps", which shows the trace
  table (step, action, why, state columns, subgoal rows). Arrow keys page when the
  walkthrough holds focus or was used last. A variant puts the two runs behind a
  segmented control and keeps the current step when switching.
- Search: a field-like trigger under the course name ("Search" with a `/` key hint; an
  icon beside the title on short desktop screens) opens a top-aligned dialog: an input, then ranked results, each with its workspace and
  place, the title and a snippet with the query words marked. Arrow keys move the
  selection, Enter opens it, Escape closes. Arriving at a result scrolls to the passage,
  outlines it briefly, opens any disclosure or walkthrough step holding the words and
  marks them with the CSS highlight `search-hit` until the next navigation.
- Exam home: the Study and Exercises home rows (title, details, status: Not started,
  In progress, Done) for the cheatsheet, each pattern and each practice paper, with
  Continue in the header. Worked-practice steps show only "Step N of M"; it links to
  the workflow step it applies, which flashes on arrival.
- Lecture highlights: optional numbered steps, each opening the recording at its time
  link, and the same Recall button as notes.
- Study references opened from exercises use the existing side panel on desktop.
  Below 1200px the modal covers the entire viewport without a background gutter;
  its close control stays reachable while the content scrolls. Closing restores
  focus and scroll to the unchanged exercise step.
- Learning definitions use the supplied stacked reference at every width: the bold
  term sits above its explanation and conditions, which use the full reading width.
  Preserve semantic definition lists, the existing quiet rule and integration into
  the current passage. Do not reserve a side column for labels or add a section
  heading, box or repeated title. Consecutive definitions remain one list.
- Exam facts: a semantic definition list directly under the page header, without
  a redundant section heading. Use full-width rows with neutral
  dividers and 12px vertical padding. Labels use `--text-ui` and `--muted`;
  values use `--text-body`. A 128px label column and 24px gap align the facts,
  with a shrinkable value column that wraps long aids and languages on phones.
  Preserve supplied facts and the “Not stated” state for missing information.
- Component preview: demonstrate section, subsection and detail headings using
  the existing heading scale, plus an untitled continuation. Lecture blocks nest
  beneath their section heading. The optional Lecture demo uses the same
  shared styles and real workspace navigation as prepared notes.
- Contents hierarchy follows the Notion reading pattern: indent each deeper
  heading by `--s3` (12px), preserving semantic nesting through h6. Returning to
  a shallower heading resets indentation. Every entry scrolls to and focuses its
  heading, including headings nested inside Lecture and exercise guidance.
  Keep the existing typeface, reading scale and themes. All heading levels reset
  browser margins and use the shared text-wrapping and scroll-offset rules.
  Reference: https://www.notion.com/help/columns-headings-and-dividers
- Pending sheets: native disclosure labelled “Not prepared yet”, a separate sheet
  count, and a short explanation when expanded. Source names and pending problem
  labels occupy distinct lines in a divided list. Closed initially; no dead links
  or disabled-looking buttons. Partial-sheet pending labels stay within their sheet.
  When no sheets are prepared, this disclosure is the main visible overview content.
- Study preparation uses the same disclosure after Topics, counted by source, never
  by invented lessons. Confirmed `gap` and `partial` outcomes appear under “Not prepared
  yet”; partial outcomes explicitly say “Partly prepared”. Unknown coverage and optional
  backlog are not learner-facing panels. The Study disclosure opens directly to its
  source list, without introductory descriptions. Fully covered and
  explicitly out-of-scope outcomes do not appear. Removed sources and other resource
  kinds do not enter the Study queue. Counts describe preparation, not student progress.
  The empty Study route also shows the recorded queue without a broken Start link.

## 6. Motion and interaction

Follow the beui shared-layout-bg mechanism of a full-item tonal surface responding
equally to pointer and keyboard focus (source: https://beui.dev/r/shared-layout-bg/raw).
Use CSS and native disclosures; no moving hover pill, spring library or new runtime.
Feedback is immediate; no positional or layout animation. Existing `--fast` (140ms)
and `--ease` (ease-out) remain available to existing controls. Reduced motion retains
all information and controls, with immediate state changes.

## 7. Accessibility constraints

All summary and link targets remain at least `--target` (44px). Preserve native
Enter/Space disclosure control and link navigation; the entire visible row is the
same destination. Text wraps at narrow widths with no horizontal overflow. Pending
content is announced as a real disclosure and list, not progress or a call to action.
  Screen-reader link names include title, metadata and progress; no fake selection.

## 8. Review and debt

Verify Study, Exercises, Exam and sibling Lecture at phone, tablet and desktop widths,
light/dark, full-row hover/focus, disclosure open/closed, navigation and scrolled end.
Exercise long source titles, long metadata, partial preparation and all-pending data.
Use synthetic local fixtures, never campus sessions. The user requires single-agent
implementation and review, overriding skill delegation. No new accepted design debt.
The screenshots define the existing visual language; their known hover and pending
defects are the requested changes, not pixel-identical targets for those states.
