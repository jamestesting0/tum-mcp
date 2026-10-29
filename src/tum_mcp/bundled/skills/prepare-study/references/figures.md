# Drawing figures

A figure earns its place when the student understands the idea faster from it than from
text. Before drawing, write the one thing it must show, such as "the agent sees only its
own room, and moving costs a point". Leave out everything that does not serve it.

## Workflow

1. Write the message in one sentence and list every label. A label names a part or gives
   a value: "Dirty", "+3 per room cleaned", "θ₁ = 90°". A vague label such as "clean or
   dirty?" says nothing; show both cases, or show one state and say which it is.
2. Sketch the layout. The eye enters top-left and follows the process left to right or
   top to bottom. Keep lines from crossing and give each part room to breathe.
3. Draw on a 320 to 400 unit wide canvas (480 at most). The app never enlarges a drawing,
   so 16-unit text reads as 16 px on a laptop and shrinks only on a phone. Labels are 16
   units, small notes 14 units; the build rejects smaller text and wider canvases.
4. Place every label next to its part, with a short leader line if it cannot touch it.
   Labels never overlap lines or other labels. Values that need a key belong in the
   caption.
5. Use few strokes and the theme classes only: `ink` for the subject, `accent` for the
   one thing to notice, `muted` for context. Text takes no stroke class.
6. Build, then look at the figure at phone and desktop widths. Read each label; if the
   message is not obvious in five seconds, simplify.

Sources: technical-diagram practice on flow, whitespace and label legibility
(https://serialized.net/2020/02/effective_technical_diagrams/), cartographic labelling
(association and conflict avoidance,
https://en.wikipedia.org/wiki/Typography_(cartography)) and readable SVG text at the
displayed size (https://www.sitepoint.com/make-responsive-svg-graphs-infographics/).
