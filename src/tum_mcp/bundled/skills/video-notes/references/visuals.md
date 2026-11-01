# Visual style

The house style is quiet and readable: the course app's current canvas and semantic
colors, one font family, few moving parts. It shares 3Blue1Brown's teaching moves,
not its look.

## Tokens

Use `self.color(token)`, never raw hex. Text tokens: `ink`, `muted`, `accent`,
`emphasis`, `positive`, `negative`, `frontier`. Shapes: `line`, `wash`, `active`,
`visited`, `background`. Six distinct series/symbol colors: `c1` to `c6`. Text on an
`active` fill must use `active_ink`. `self.symbol(name)` returns a symbol's course
color from `videos/style.json`, or `ink`. Tokens meet 4.5:1 for text and 3:1 for
graphics against the background in both themes. New projects default to `light`;
explicit `dark` remains supported. MP4s have a fixed theme, independent of the app.
CSS declarations are authoritative and staged into the worker, not copied into a
second palette. Never signal by color alone: pair a color with a label, outline,
position or a named state.

Diagram states follow the app: active is filled `active`; visited is filled
`visited` with an `accent` outline; frontier is a thick `frontier` outline.

## Layout

The frame is 14.2 by 8 units. Keep text inside the safe box: 0.3 units from the
sides and top and out of the bottom 12% (below y = -3.04). Named
regions (`self.region(name)` returns left, right, bottom, top): `title`, `main`,
`left`, `right`, `note`. `self.anchor(row, column)` returns the centre of a 6 by 6
grid cell inside the safe box (row 0 at the top); place items on anchors or next to
their target with `next_to`, not at arbitrary coordinates.

Minimum sizes are enforced: labels and numbers 24, math 30, code 20. Prefer 32 for
labels and 40 to 48 for primary math. After `scale()`, text below 90% of the
minimum is reported. Text never overlaps other text; dim context beside new content
(opacity about 0.15) and fade out anything that new content will cover. If a
deliberate overlap is right (a label on its node is not text-on-text), add a
`layout_waiver` with the reason to that beat.

Measure labels rather than guessing how many characters fit. `self.label(key,
width=...)` wraps at the requested scene width without reducing its font size.
If the wrapped text is too tall, shorten or recompose the scene, move a supporting
view, or continue in another beat. Do not shrink the whole diagram to accommodate
a long sentence. Keep one clear hierarchy between section, knowledge point,
working and final result.

Use the layout the content needs: a readable givens table for the actual problem,
aligned working for a derivation, explicit state for an algorithm, and a distinct
final answer after verification. Keep related objects and reused results in stable
places. Inspect the real video at its viewing size; a full-resolution font minimum
does not establish that a detailed landscape frame is readable inline on a phone.
The safe box is a geometry minimum, not proof of caption clearance. Check paused
playback with captions and native controls visible, including phone fullscreen.
Move bottom rows or recompose the view when those overlays cover teaching; do not
hide captions or reduce the type to make the check pass.

## Motion

- First appearance: `Create` for shapes, `Write` or `FadeIn` for labels and math.
- Equation steps: `TransformMatchingShapes` between math items; group parts with
  `{{ ... : name }}` in Typst and color them by symbol.
- Emphasis: `Indicate` or `Circumscribe`, sparingly, on the thing being named.
- Reveal and highlight the current step at its sentence cue. Do not pre-fill
  later calculation results or state updates. Final answer emphasis follows the
  explanation; it is not a substitute for the visible reasoning.
- Sequences: `LaggedStart`; traversals: `MoveAlongPath` or state recolors per frame.
- Camera moves only when zooming adds clarity.
- Typical durations 0.6 to 1.5 seconds with smooth easing. No more than three
  flashes per second; no strobing.

## Per block type

| Prepared block | Treatment |
| --- | --- |
| diagram | Rebuild nodes from the block's x and y, scaled into `main`; animate frames as state changes with a non-color cue. |
| formula | Build term by term after the concrete instance; symbol glossary as labels; conditions as a side note. |
| uml | Redraw the class or sequence diagram in the same notation; reveal classes or messages in order, keeping UML arrowheads and dashes exact. A state diagram enters state by state along its transitions. |
| plot | Axes with the source labels and units; draw series in order; sweep a parameter only when the formula defines the function exactly. |
| code | `self.code(key)` lines with a moving highlight and a small variable table driven by storyboard numbers. A prepared walkthrough gives the order of highlights. |
| files | Show only the file and lines the beat explains, as code; never scroll through a whole project. |
| tree | Grow the tree level by level from the root, keeping indentation and connector lines; reveal notes such as sizes as the beat reaches them. |
| table | Reveal rows against the comparison criterion; highlight contrasting cells. |
| text points | Narration plus objects, not bullet slides. |
| cards and questions | Question beats and pitfalls; distractor feedback names misconceptions. |
