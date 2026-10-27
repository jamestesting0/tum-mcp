# Visual style

The house style is quiet and readable: a dark navy canvas from the course app's
palette, one font family, few moving parts. It shares 3Blue1Brown's teaching moves,
not its look.

## Tokens

Use `self.color(token)`, never raw hex. Text tokens: `ink`, `muted`, `accent`,
`emphasis`, `positive`, `negative`, `frontier`. Shapes: `line`, `wash`, `active`,
`visited`, `background`. Six distinct series/symbol colors: `c1` to `c6`. Text on an
`active` fill must use `active_ink`. `self.symbol(name)` returns a symbol's course
color from `videos/style.json`, or `ink`. Tokens meet 4.5:1 for text and 3:1 for
graphics against the background in both themes (`theme: light` exists for courses
that need it). Never signal by color alone: pair a color with a label, outline,
position or a named state.

Diagram states follow the app: active is filled `active`; visited is filled
`visited` with an `accent` outline; frontier is a thick `frontier` outline.

## Layout

The frame is 14.2 by 8 units. Keep text inside the safe box: 0.3 units from the
sides and top and out of the bottom 12% (the caption band, below y = -3.04). Named
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

## Motion

- First appearance: `Create` for shapes, `Write` or `FadeIn` for labels and math.
- Equation steps: `TransformMatchingShapes` between math items; group parts with
  `{{ ... : name }}` in Typst and color them by symbol.
- Emphasis: `Indicate` or `Circumscribe`, sparingly, on the thing being named.
- Sequences: `LaggedStart`; traversals: `MoveAlongPath` or state recolors per frame.
- Camera moves only when zooming adds clarity.
- Typical durations 0.6 to 1.5 seconds with smooth easing. No more than three
  flashes per second; no strobing.

## Per block type

| Prepared block | Treatment |
| --- | --- |
| diagram | Rebuild nodes from the block's x and y, scaled into `main`; animate frames as state changes with a non-color cue. |
| formula | Build term by term after the concrete instance; symbol glossary as labels; conditions as a side note. |
| plot | Axes with the source labels and units; draw series in order; sweep a parameter only when the formula defines the function exactly. |
| code | `self.code(key)` lines with a moving highlight and a small variable table driven by storyboard numbers. |
| table | Reveal rows against the comparison criterion; highlight contrasting cells. |
| text points | Narration plus objects, not bullet slides. |
| cards and questions | Question beats and pitfalls; distractor feedback names misconceptions. |
