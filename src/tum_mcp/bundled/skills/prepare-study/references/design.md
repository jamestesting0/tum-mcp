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

The app uses index.html, styles.css, app/dom/mathml/navigation/reading/formulas/learning/question-review/flashcards/
revision, anchors/comments/comment-ui/comment-store/comment-popover.mjs, the font-*.woff2
subsets with fonts-license.txt, and generated data.mjs. Author content.json; extend shared components only for a real course need,
with validated data, safe rendering and accessible fallback. No CDN fonts, scripts,
analytics or campus credentials. Keep local module preloads and preview compression so
the first reading view is not delayed. Keep previews local unless publication is
requested. Use [verification](verification.md), not screenshot count, as the gate.
