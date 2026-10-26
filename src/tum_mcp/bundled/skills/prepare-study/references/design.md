# Study design contract

Use the bundled renderer and tokens; preserve an established custom theme. The site is
a quiet reading tool: one course outline, one focused unit, and the learning activity
as the focal object. Visible text supports learning or navigation. Keep sources and
essential assumptions; remove promotional or admin copy, technical banners, repeated
tips and mastery claims. Use short sentence-case labels such as Save, Continue and
Try again. Component contracts live in [components](components.md).

## Tokens

| Token | Light | Dark |
| --- | --- | --- |
| --canvas | #ffffff | #101a28 |
| --surface | #f7f9fb | #152236 |
| --aside | #f2f5f8 | #0b1420 |
| --ink | #072140 | #e9eef5 |
| --muted | #526477 | #aabbd0 |
| --line | #d8e1e9 | #344253 |
| --accent | #3070b3 | #8cbffa |
| --wash | #eaf2fa | #203b55 |
| --error | #9b3d37 | #ffb4a7 |
| --warning | #f5eddd | #3d3327 |

Blue/navy derive from [TUM's stylesheet](https://www.tum.de/typo3conf/ext/in2template/Resources/Public/Css/styles.css).
Use these fixed values; do not repeat reference-site research. One accent, neutral 1px
rules, no gradients, shadows or coloured edge stripes. State uses wash, weight and a
text label or glyph; correctness is never shown by color alone.

## Type and space

- One bundled primary typeface (OFL, `fonts-license.txt`): Atkinson Hyperlegible
  Next for headings, reading and interface text. It distinguishes similar letters
  and numerals. Use weight 600 for the page title, 500 for section headings and
  controls, and 400 for reading text. Do not mix decorative heading families.
  Local woff2 subsets use unicode-range and font-display swap; no webfont service.
  Code retains the system monospace stack (`--font-mono`); formulas retain native
  math fonts for correct notation. These are functional exceptions, not UI styles.
- Sizes: reading 18px/1.7 (questions and options 18px/1.5); dense blocks (tables, code,
  glossary, objectives) and interface 15px; labels 14px. Titles 32–44px, sections
  24px; card text 28px, 18px on phones. Weights 400/500/600. Labels use sentence case
  without letter spacing; only the page title tightens (-0.015em). Numerals are lining.
  Preserve technical terms and notation.
- Spacing 4/8/12/16/24/32/48/64px. Controls 6px radius, content surfaces 12px.
- Math uses `--math-max` (24px) and `--math-min` (18px). Equations adapt to their
  container, including outline changes: reflow chained relations at the top level,
  then fit each complete line. Keep fractions, matrices and grouped expressions
  intact. An indivisible oversized expression gets local scrolling, never clipping
  or unreadably small text. Recompute after font loading and width changes.

## Layout

- One reading column: the 66ch prose measure plus 48px side padding on desktop.
  Header, tabs, cards, practice and the next-step link share that column.
- Desktop: 248px outline, fully hidden when collapsed, with no rail. Main owns reading
  scroll; long outlines scroll independently. No toolbar.
- Below 800px: single document scroll and 20px side padding. A collapsed outline is a
  sticky bar with the menu button, the current title and a 1px bottom rule; scroll
  padding keeps anchored content below it. Choosing a unit collapses the outline.
  Opening it shows a fixed viewport overlay with its own scroll, immediately visible
  from any reading position. Keep the reading position, make the background inert,
  trap keyboard focus inside, and return focus on close/Escape. Do not insert the
  expanded outline into the document flow or require a scroll to reach it.
- Grid children have min-width/min-height zero. Long names wrap, including outline
  summaries. Primary content never scrolls horizontally. Wide tables, formulas and
  code use labelled keyboard-scrollable regions; diagrams fit the column.
- Study outline labels and titles share a row when they fit; wrap at the available
  width and keep progress on its own line. Revision Topics uses the shared compact
  disclosure button and chevron, with a 44px target and native keyboard behavior.

## Motion

Controls respond immediately: opacity/press 140ms ease-out, optional 0.99 scale. The
card turns 180deg around Y over 240ms with hidden backfaces. The inactive face also
switches to `visibility: hidden` at mid-turn, because WebKit can paint a hidden
backface. The next-step arrow moves 4px on hover. Theme colors switch immediately.
Reduced motion removes the turn, the nudge and transitions. No autoplay, scroll-driven
or decorative motion.

## Access

Target WCAG 2.2 AA: visible focus-visible rings, landmarks and skip link, labelled
44px controls, keyboard operation, text alternatives and aria-live state/feedback.
Programmatic focus targets (headings, legends) use tabindex -1 without a ring.
Essential information never depends on hover. Messages name an actual gap or error.

## State and storage

Progress, theme, revision selection and the last visited view stay local per course.
Storage failure shows a visible conditional warning and keeps in-memory practice.
Reset lives on the course home and needs confirmation in an app dialog; it clears this
course's ratings and answers and keeps comments and topic choices. Changed unit
revisions never inherit old answers. Grouping or moving folders never resets progress.
Preserve customized renderer files and user notes.

## Files and extension

### Shared Study and Exercises states

Both preparation skills use the same course renderer. When both workspaces are
prepared, the only workspace switch is a compact selector pinned at the bottom
of the sidebar. Use a rounded square workspace glyph, name and chevron; open an
upward menu with the two workspace names and an explicit current indicator. Keep
theme as an adjacent quiet icon. The outline body scrolls independently above it.
Category rows use a small chevron and compact spacing with a 44px click target;
keep native collapse/keyboard behavior and wrap long names. Use a neutral category
hover, a 4px gap before children, and rounded selected child rows so parent and
selection never merge into one colored block.
On phones this same footer appears inside the open outline overlay. No heading
switch, duplicate navigation links or second toolbar. Support keyboard navigation,
Escape, outside dismissal and focus return. A lone workspace has a passive label.

Exercises uses category headings and expandable sheets with direct numbered task
links. The original statement comes first. Guidance and worked solutions are
native disclosures; one active conceptual step uses the existing control/feedback
styles. Use a compact step counter with arrow navigation beside it, a clear prompt,
flat radio rows, and one primary action. Use short visible Check, Compare, Hint,
Explain and Solution labels. Secondary actions have a quiet outlined button surface;
Previous/Next are labelled arrow buttons in a persistent, sticky step header.
Change only the active step body; preserve control position and keyboard focus
when moving between steps. Do not add back links duplicating the
outline or scrolling. Keep sources behind the small book icon beside each section
title, with full locators available on demand. One help button reveals successive hints,
then step reasoning, inline without moving focus or advancing. Avoid stacked
bordered cards and repeated disclosure/navigation rows. Tables use real headers and
labelled editable cells with local scrolling. Math/code use generous multiline work
areas and rubric comparison; never claim automatic proof or program grading.
Graph questions use the drawing itself for keyboard/touch node/edge/path
selection. Line graphs support axes, source-backed series and editable plotted
sample points with numeric/keyboard alternatives. Preserve drafts and invalidate verdicts whenever an answer changes. Keep one primary
Check / Compare / Continue action. Navigation stays in the step header.
Paper work is valid. Show only Not started, In progress, or Reviewed in lists.
Reviewed records a voluntary review action, never mastery or an official result.
Use existing focus, source-note, safe-block, reduced-motion and storage-warning
patterns. Preserve scroll and typed work when switching workspace or visiting a
prerequisite. Closed solutions stay outside the accessibility tree.

The app uses index.html, styles.css, app/dom/mathml/navigation/reading/formulas/learning/question-review/flashcards/
revision, anchors/comments/comment-ui/comment-store/comment-popover.mjs, the font-*.woff2
subsets with fonts-license.txt, and generated data.mjs. Author content.json; extend shared components only for a real course need,
with validated data, safe rendering and accessible fallback. No CDN fonts, scripts,
analytics or campus credentials. Keep local module preloads and preview compression so
the first reading view is not delayed. Keep previews local unless publication is
requested. Use [verification](verification.md), not screenshot count, as the gate.

### Optional Lecture Notes

The optional Lecture extension adds a third workspace in the existing sidebar
selector. Lecture Notes uses recent-first dated lecture rows, overview/takeaways
and coherent topic sections in the same reading column. Reuse safe block bodies
for formulas and explanatory diagrams. No activity tabs, ratings or reset control.
Keep timestamp/range links quiet beside sections and measured capture-time links
beside figures. Captures retain dimensions, alt/caption, lazy loading and a
keyboard-accessible original-size link. Put attribution/additional-explanation
review in private metadata; no visible AI-added labels. Partial coverage/as-of
information stays secondary, with detail available on demand.
