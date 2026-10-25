# Study space design contract

Use this system for new study sites. Preserve a user's established custom theme
when extending one. Keep learning content separate from layout and interactions.

## 1. Identity

A quiet course notebook: a clean reading surface, precise diagrams, generous reading space.
The signature is a stable course outline beside one focused learning unit.
Use content, flashcards and practice as peer views of that same unit. Show the
source and learning objective where they help the student, without admin clutter.
No marketing hero, decorative imagery, gamification streaks or completion claims.
Visible copy must help learning or navigation. Remove technical status labels,
privacy boilerplate, platform descriptions and repeated study tips from the
reading surface. Put reset/theme preferences in concise study controls. Preserve
source citations and important learning assumptions.

## 2. Color tokens

| Token | Light | Dark | Role |
| --- | --- | --- | --- |
| --canvas | #ffffff | #101a28 | Reading background |
| --surface | #f7f9fb | #152236 | Diagram, equation and recall surfaces |
| --aside | #f2f5f8 | #0b1420 | Course outline |
| --ink | #072140 | #e9eef5 | Main text |
| --muted | #526477 | #aabbd0 | Secondary text, readable labels |
| --line | #d8e1e9 | #344253 | Neutral 1px rules |
| --accent | #3070b3 | #8cbffa | Links, active controls, diagram state |
| --wash | #eaf2fa | #203b55 | Selected or correct state |
| --error | #9b3d37 | #ffb4a7 | Incorrect feedback, always labelled |
| --warning | #f5eddd | #3d3327 | Incomplete source checks |

TUM reference: the live [TUM stylesheet](https://www.tum.de/typo3conf/ext/in2template/Resources/Public/Css/styles.css) defines brand blue #3070B3 and dark navy #072140. Use that family with the quieter surfaces above. Keep this original study layout, not the homepage navigation or promotional sections.

Use one accent. Never encode meaning through color alone. Selected rows use a
wash and a textual/glyph indicator. No accent stripes, underlined active tabs,
accent card borders, gradients or large colored backgrounds.

## 3. Typography and reading

Use local fonts. UI/body: Avenir Next, Segoe UI, system sans-serif. Headings:
Georgia, Cambria, serif. Native math may use the browser's math font. No web font
request. Body 18px/1.7; secondary 14px/1.5; UI 15px/1.45. Page title scales 32–44px,
section headings 24–28px. Use 400/500/600 weights and calm sentence case.
Limit prose to 66ch. Break long explanations by concept, not arbitrary card grids.
Keep necessary technical terms and define them once. Tables and formulas must
remain usable at 200% zoom and narrow widths.

## 4. Spacing and layout

Base spacing is 4px: 4, 8, 12, 16, 24, 32, 48, 64. Radius: controls 6px,
content surfaces 12px. Neutral 1px borders and tonal separation, no shadows.
Desktop: 248px outline, fluid main, 900px reading region, 48–64px main padding.
The main pane owns reading scroll; outline scroll is only for a long unit list.
Use min-width/min-height zero on grid children. Header tools remain available.
Below 800px: one document scroll, collapsible course outline, 20px side padding.
Tabs wrap or fit; there is no horizontal scroll of primary content.
A wide equation or table may have a labelled keyboard-scrollable region.

## 5. Primitives and states

- Course outline: course title, semester, unit labels/titles, current-unit state.
  Label the organization as Topics, Lectures or Weeks. Do not mix conventions.
- Unit heading: unit label, title, short purpose, estimated reading time, objectives.
- View tabs: Content, Flashcards, Practice. Semantic tab roles, roving tabindex,
  ArrowLeft/ArrowRight/Home/End support. Selected view uses a blue wash.
- Reading section: heading, short prose/list, compact source locator disclosure.
- Equation: native MathML with a plain-language equivalent, symbol glossary,
  assumptions and a worked interpretation. Do not use a screenshot of a formula.
  Center the expression; definitions sit below it, not inside a cramped tooltip.
- Diagram: labelled SVG or another accessible native visual, a text explanation
  and explicit state labels. For processes, use step controls, queue/state values
  and a caption that explains what changed. No automatic animation or autoplay.
- Table: caption, column/row headers, neutral rules, aligned numbers. Use a table
  for comparisons and data, not page layout. Preserve a readable mobile fallback.
- Flashcard: one retrieval prompt, deliberate reveal, then Again/Got it self-rating.
  Show the answer and sources before rating. No accidental answer on the front.
- Practice: one clear question at a time, semantic radio group, explicit Check
  answer button. Show why the chosen answer is right/wrong and explain the
  misconception. Keep feedback until Next question; never advance automatically.
- Empty/error: say what is absent or invalid and give a next action. Preserve
  working content on a failed update. A source gap is not a zero-result claim.

## 6. Interaction and progress

Use same-frame control feedback. Opacity transitions: 140ms ease-out. Theme and selected-color changes are immediate.
Optional small press scale: 0.99. No moving backgrounds or entry sequences that
hide reading content. Reduced motion keeps state changes immediate or fades.
Focus mode removes the outline, not navigation or escape controls. Theme choice
and learning progress stay in localStorage. Show a storage warning only when progress cannot be saved. Use course/unit/content revision keys so a revised
question does not inherit an old answer. Correctness is practice feedback, not
proof of mastery. Give a reset option that clears only this course's progress.

## 7. Extendability

Use the bundled static renderer as a starting point: index.html, styles.css,
app.mjs, dom.mjs, reading.mjs, learning.mjs and generated data.mjs. Agents author study/content.json. Renderer
functions share tokens and components; no copied per-unit HTML. Add a block
kind only when the course needs it, with schema, safe rendering and keyboard/
text fallback. Do not fetch CDN scripts, fonts, analytics or course credentials.

## 8. Accessibility and verification

Target WCAG 2.2 AA: readable contrast, visible focus, logical landmarks, skip
link, labelled controls, keyboard reachability, 44px targets and text alternatives.
Explain diagram state changes through aria-live. Do not rely on hover to reveal
required content. Verify phone/tablet/desktop, light/dark, reduced motion, keyboard,
long labels, empty lists and formula/table overflow on a real browser.
Keep source/course content private and preview locally unless publication is
explicitly requested. Record any actual unresolved issue; do not invent a pass.
