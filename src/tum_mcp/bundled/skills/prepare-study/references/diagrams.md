# Diagrams: graphs, UML and flowcharts

A diagram earns its place when its structure says something the text cannot say as
quickly: who depends on whom, what follows what, which path the algorithm takes. Write the
diagram's message in one sentence first; every node and edge must serve it.

## Choose the form

| The idea | Block |
| --- | --- |
| A network, map, chain over time, search graph, Bayes net, MDP, concept map | `diagram`: you place each node in a row and column |
| An algorithm with a branch or a loop | `uml` with `diagram: flowchart` |
| A linear procedure without branches | Numbered `steps` in a text block, not a flowchart |
| Classes and their relations | `uml` with `diagram: class` |
| Messages between objects over time | `uml` with `diagram: sequence` |
| Behaviour that changes with events | `uml` with `diagram: state` |
| A physical or spatial shape (an arm, rooms, a circuit) | `figure`, as in [figures](figures.md) |

The app draws every one of these from structure. You never give pixel positions.

## Graph diagrams

The `diagram` block keeps your arrangement and does the geometry: it sizes nodes from their
labels, spaces rows and columns, bends a blocked edge around nodes to the side where it
crosses fewest edges, bows the two arrows of a two-way pair apart, draws a self-loop on the
node's freest side, and places each edge label clear of every line and node. On a narrow
screen the drawing shrinks until its labels reach 12 px; beyond that it scrolls sideways.

1. **Lattice first.** Decide the rows and columns before anything else. Every node takes
   its own cell (`row`, `col`, both 0 to 5). Nodes that relate share a row or a column.
   Plan for a phone column of about 320 px: a row holds about three circles joined by
   weights, or two boxes with a worded edge between them. Put a third box on the next row.
2. **Reading order.** The main flow runs along one row (time, sequence) or down one column
   (causes above effects, parents above children). List nodes in that order.
3. **Neighbours next to each other.** An edge joins neighbouring cells where it can. A long
   edge that would cross a node's cell gets bent around it, but a straight edge between
   neighbours reads faster: move the node rather than rely on the bend.
4. **Keep meaning in place.** When position carries meaning (a map, a timeline, a ring),
   keep it: snap it to the lattice, never rearrange it for neatness.
5. **Short labels.** Circles hold up to four characters; boxes a short name that fits on two
   lines. Edge labels are weights or a few words ("stop: 3", "signals"). A loop that stays
   in place is a self-loop (`start` = `end`), never an invented node.
6. **Two-way relations.** Two directed edges between the same pair bow apart, each with
   its label outside its own arc. Use one undirected edge when the relation is symmetric.
7. **Colour with frames.** Mark the one node the caption is about as `active` and its
   context as `visited`; never mark everything.

## UML

- **Keep the model whole.** Never leave out a class, relation, state or message to make the
  picture tidier; a missing element is a wrong diagram. Fix the picture with order instead.
- **Order is layout.** The app keeps the order you list things in. Classes: supertypes
  before subtypes, clients after what they use. Relations: generalizations first. States:
  the initial state, the main path, side states, then the final state; transitions on the
  main path before back edges.
- **Notation.** Members as UML writes them (`+ update(s: Subject): void`). A whole-part
  relation names the part's role. A state's entry action goes in `activity`
  (`entry / start audio`). Transition labels read `event [guard] / effect` and stay short.
- **Sequence diagrams.** Participants in call order, at most about five; short message
  signatures, with the types explained in the text; fragments (`alt`, `loop`) over the
  messages they cover.

## Flowcharts

Use a flowchart only where a branch or a loop is the point; a straight procedure is a
numbered list. One `start`; `end` steps named by their outcome ("Consistent",
"No solution"). Steps are short commands ("Remove arc (X, Y)"); a decision is a question
("Queue empty?") and every exit carries its answer ("yes", "no"). List steps in execution
order, and the main path before the loop back.

## Check

Build, then run `tum-mcp study visuals PROJECT --unit KEY`. It draws every diagram at
phone, narrow and desktop width, reports what it measures (an edge through a node, labels
that overlap or sit on a line, text under 12 px, a drawing that differs from its block)
and writes contact sheets to `.tum-mcp/visuals/`. Open the sheets and look. A diagram
passes when a student can follow its main path without reading the caption, no label
touches a line or another label, it fits a phone or scrolls only because it cannot be
narrower, and nothing contradicts the source. When it fails, change the content (cells,
order, labels), never the renderer. review-course scores the result on its
[visual rubric](../../review-course/references/visuals.md#rubric).

## Mistakes found in real courses

- A Bayes net drawn as a straight row: the Rain → Wet edge ran behind Sprinkler and the
  picture showed a chain. Put the parents beside each other above the child.
- "Continue" drawn as a node although it is an action that returns to the same state: use
  a self-loop.
- A decision tree given as a table: draw it as a diagram with one row per depth.
- A class diagram that dropped the client class to look tidy: list the classes in a better
  order instead.
- Long method signatures on sequence messages: shorten them and explain the types in text.
- Three boxes with worded edges in one row: wider than a phone, so it scrolls. Move the
  third box to the next row.

## Sources

- [D2 grid diagrams](https://d2lang.com/tour/grid-diagrams/): place in rows and columns;
  elements in a column share a width.
- [C4-PlantUML layout guidance](https://plantuml-stdlib.github.io/C4-PlantUML/LayoutOptions.html):
  create elements in reading order; add the fewest hints; back out hints that change nothing.
- [ELK layered algorithm](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html),
  which lays out the app's UML and flowcharts in the order the author lists elements.
- Purchase (1997): edge crossings hurt comprehension most, then bends.
