# Drawing figures

A figure earns its place when the student understands the idea faster from it than from
text. It shows one message, such as "the agent sees only its own room". Leave out
everything that does not serve that message.

## Workflow

Shapes come first and labels last: placing both at once makes every move break something
else.

1. **Message and label list.** Write the message in one sentence. List every label; each
   names a part or gives a concrete value ("Dirty", "θ₁ = 90°", "(0, 2)"). A label such
   as "clean or dirty?" says nothing: show one state and name it.
2. **Shapes.** Draw on a canvas 320 to 400 units wide (480 at most). Read the figure left
   to right or top to bottom. Give lines that run side by side at least 12 units of space
   between them, and avoid crossings. Physical figures keep their true geometry: an arm
   link or a ball's path may be diagonal.
3. **Labels.** Place each label beside its part, on empty canvas:
   - Put the label at the free end of a line, or beside a point on the side away from the
     other strokes. Never put it on a line or in the narrow gap between two lines.
   - Keep each label 5 units clear of every stroke, filled shape and other label, and
     inside the canvas.
   - Point labels go outside the shape they belong to; a part label may sit inside a box
     or circle if it clears the outline.
   - Labels are 16 units, notes 14 units. Prefer a direct label to a legend; use the
     caption for anything that needs a key.
4. **Style.** Use the theme classes only: `ink` for the subject, `accent` for the one
   thing to notice, `muted` for context, `dashed` for planned or hidden paths. Do not add
   decoration.
5. **Check.** The build estimates every label's box and rejects labels that touch a
   stroke, sit on a filled shape, overlap another label or leave the canvas; move the label,
   never the rule. Then look at the figure in dark mode at phone and desktop widths when
   the host can render pages. If the message is not obvious within five seconds, simplify.

The app draws each label on a small halo of the page colour and never shows a figure wider
than its canvas, so 16-unit text reads as 16 px on a laptop. The halo is a safety net, not
a reason to place labels on lines.

## Sources

Taken from open-source drawing skills and layout research; adapted for small teaching
figures:

- [diagram-design](https://github.com/cathrynlavery/diagram-design): a label never sits on
  its line and keeps a visible 6 to 10 px gap; no two strokes share or crowd a path (12 px
  apart); its render linter treats the browser as the authority on what is painted.
- [fireworks-tech-graph](https://github.com/yizhiyanhua-ai/fireworks-tech-graph): one
  dependency-free geometry contract shared by the generator, the checker and CI; labels
  are moved off strokes first, with a backing only as a fallback.
- [Penrose staged layout](https://penrose.cs.cmu.edu/blog/staged-layout): lay out shapes
  before labels; keep point labels near their point and outside the shape.

Deliberately not adopted: orthogonal-only connectors (wrong for physical figures),
7 to 12 px label sizes (unreadable on a phone), web fonts and brand palettes (the app is
offline and themed), and fixed 80 px architecture spacing (too large for a 400-unit
teaching figure).
