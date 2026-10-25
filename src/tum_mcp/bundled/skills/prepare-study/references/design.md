# Study design contract

Use the bundled renderer and tokens; preserve an established custom theme. One
course outline and one focused unit, with Content/Flashcards/Practice peer views.
Visible text must support learning/navigation. Keep sources and essential assumptions;
remove promotional/admin copy, technical banners, repeated tips and mastery claims.

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
Use these fixed values; do not repeat reference-site research. One accent, neutral
1px rules, no gradients/shadows/accent stripes. Selection uses wash, emphasis and
semantic state; correctness also has a text label, never color alone.

## Geometry and type

- Local fonts: Avenir Next/Segoe UI/system sans; Georgia/Cambria headings; native math.
  Body 18px/1.7, secondary 14px/1.5, UI 15px/1.45. Titles 32–44px, sections 24–28px;
  weights 400/500/600. Prose ≤66ch; preserve technical terms and notation.
- Spacing: 4/8/12/16/24/32/48/64px. Controls 6px radius, content surfaces 12px.
- Desktop: 248px outline, fluid main with a ≤900px reading region and 48–64px
  padding. Main owns reading scroll; long outlines scroll independently.
- Below 800px: single document scroll, collapsible outline, 20px side padding.
  Grid children have min-width/min-height zero. Long names wrap, including outline
  summaries. Primary content never scrolls horizontally; wide tables/formulas/code/
  diagrams use labelled keyboard-scrollable regions with legible text, also at zoom.

## Learning components

| Component | Contract |
| --- | --- |
| Outline/heading | Course + semester, consistent lecture/week/topic labels, current unit; title, purpose, estimated time and optional objectives. |
| Tabs | Semantic tablist/tabs/panels; all target IDs exist. One active panel, roving tabindex, arrow/Home/End keys. |
| Source | Compact disclosure with a usable link and locator. No unnecessary personal/contact information. |
| Formula | Native MathML, readable equivalent, symbol/unit glossary, assumptions and interpretation. No formula screenshots. |
| Visual | Accessible SVG/native visual plus explanation. Processes have explicit steps/captions, labelled state and no autoplay; concept maps need no fake traversal controls. |
| Table/code | Tables have caption and column/row headers. Code is literal, labelled by language and explained. Wide content remains usable without breaking the page. |
| Card | Retrieval before reveal; answer/sources then Again/Got it. One idea per card; no answer leaked on its front. |
| Practice | One question, native radio group, explicit Check answer; retained feedback explains choice and alternatives. Retry/next are deliberate. |

## State, access and extension

Controls respond immediately; only opacity/press motion may transition (140ms
ease-out, optional 0.99 scale). Theme/selected colors switch immediately; reduced
motion removes movement. Focus mode retains navigation and an Escape/exit control.
Progress/theme stay local. Storage failure leaves a visible conditional warning and
working in-memory practice. Reset affects this course only; changed unit revisions
must not inherit old answers. Preserve customized renderer files and user notes.

Target WCAG 2.2 AA: visible focus, landmarks/skip link, labelled 44px controls,
keyboard operation, text alternatives and aria-live state/feedback. Essential
information cannot depend on hover. Keep UI messages specific to an actual gap/error.

The app uses index.html, styles.css, app/dom/reading/learning.mjs and generated
data.mjs. Author content.json; extend shared components only for a real course
need, with validated data, safe rendering and accessible fallback. No CDN fonts,
scripts, analytics or campus credentials. Keep previews local unless publication
is requested. Use [verification](verification.md), not screenshot count, as the gate.
