# Content and build contract

`tum-mcp study schema content` is the authoritative input schema. Redirect it to a
private file and read only the definitions you need. The synthetic demo
(`tum-mcp study demo PROJECT`) shows each block type in use; inspect only the
relevant object, and author real lessons from reviewed course sources.

Edit `app/content.json` (legacy `study/content.json`). Preserve unaffected unit
objects and stable keys. Build installs the app and generates `data.mjs`; ordinary
content edits need no HTML, CSS or JavaScript inspection.

## Course and units

Top level: `schema_version`, `course_key`, `organization` (lectures, weeks or topics),
`introduction` and `units`. The introduction opens the course home: one or two
sentences on what the course covers and where to start.

Units carry key, label, title, summary, minutes, objectives, sources, blocks,
flashcards and questions. Sources pair an inventory resource key with its exact
current SHA-256 from state, and every citation uses a declared key. Keep source
titles short and locators precise; students see them in a compact sources list.
Group units with `path` so the outline folds them: one label per unit naming the
lecture, week or topic of the course's `organization`, for example
`["Lecture 2 · Intelligent agents"]` for every unit taught from lecture 2. Units of one
lecture share the label; `study report` flags a flat list of four or more units. Use a
second level only for a large group. Do not add a course-name folder inside its own
site. Keep existing unit labels and keys so progress survives; moving folders never
changes progress.

## Explore

Optional `explore` items use their own versioned sources and keyed reading blocks.
Read [Explore](explore.md) for fields, classification, source scopes and review. Leave
it absent/empty when the unit needs no supporting material; do not weaken core
objectives or practice. Optional-only edits preserve core progress while invalidating
changed optional reviews and comments.

## Notation

Every symbol, variable, formula and calculation in teaching text is inline LaTeX in
`\( ... \)`: paragraphs, steps, points, objectives, table cells, symbol definitions,
card faces, question options and feedback. JSON escapes the backslashes:
`"Use \\(v_i\\)."`. Build validates them; the app typesets them with KaTeX, as Notion does.

- Greek letters, relations and operators: `\(\gamma\)`, `\(0 \le \gamma < 1\)`,
  `\(x \neq y\)`, `\(\forall x\, P(x)\)`, never γ, ≤, ≠ or ∀ as characters.
- Conditionals and functions: `\(P(A \mid B)\)`, `\(Q(s, a)\)`, `\(\log_2 p\)`.
  Word operands take `\mathrm{}`: `\(e = \mathrm{output} - \mathrm{reference}\)`.
- Calculations: the whole line, `\(1 + 0.5 \times 3 = 2.5\)`, so the student reads one
  expression. `study report` still recomputes it.
- Sub- and superscripts: `\(V_0(S)\)`, `\(b^{*}\)`, `\(2^{2}\)`, never V₀ or b*.
- Once a unit introduces a notation, write its formulas in it, not in words: `\(\neg P
  \lor Q\)`, not "not P or Q"; `\(P(R \mid C)\)`, not "rain given cloud". `study report`
  cannot see a formula spelled out in words.

Show the object, never describe it: write \(P = \begin{pmatrix}1 & 0\\ 0 & 0\end{pmatrix}\),
not "the diagonal matrix with entries 1, 0"; a vector, table or graph likewise appears
itself, and the sentence says what to notice in it. `study report` flags described objects
as `described_object`. Inside a sentence, a column vector of up to three entries or a
matrix up to 2x2 reads well: the line grows to fit it, and long inline math wraps after
`=` or `+`. Write a ket as `\lvert 0\rangle` or `|0\rangle` and a square root as
`\sqrt{2}`; KaTeX sets them as in TeX. Anything larger goes in a formula block (`tall_inline_math`).
Use `\lvert`/`\rvert` and `\mid` for bars; `\left( ... \right)` stretches fences around
a fraction.

Convert complete mathematical tokens, never letters inside ordinary words, and reread
the prose after notation edits. Long equations belong in formula blocks. Keep source
titles and outline labels plain. Diagrams and figures have no LaTeX renderer; their
labels use Unicode, such as θ₁ or γ = 0.5. Dollar signs stay literal; code blocks and
comments never interpret markup. `study report` flags plain-text mathematics as
`plain_math`.

Wrap identifiers, method names, short expressions in code and file names in single
backticks in the same teaching text: `` `getChildren()` `` renders as inline code in
every workspace. Text inside backticks stays literal, including `\(`. Use a code
block for anything longer than one line.

## Blocks

Every block has sources. Its `title` and `level` build the page outline:

- A titled block opens a section at its `level`: 1 a section, 2 a subsection of the
  section above, 3 one below that. Headings start at 1 and go one level deeper at a
  time; the build rejects a skipped level. Use a subsection for one step of a bigger
  idea (the cases of a definition, the parts of a worked example), not for every block.
- An untitled block continues the section above it under that heading and citation:
  the table, figure or answer frame that belongs to the passage before it. Title a
  block only when it starts something the student would look for in the outline.
- Exercises, Exam and Lecture use the same blocks and rules. In Lecture,
  each section is already the top level, so its blocks sit one level below.

Plan the outline before writing the blocks: a level-1 topic, level-2 cases or worked
examples that belong to it, and level-3 detail only when that case needs another division.
For example, "Propagation" (1), "Revise an arc" (2), "An empty domain" (3), then
"Exploit structure" (1). Use that relationship, not font size, to choose levels.
Flattening every short passage to level 1 hides which examples support which method.
Do not use every level by quota, add empty parent headings or give definitions their own
sections; an untitled figure or table often belongs directly under the existing heading.
Apply this outline check in all four workspaces, including rich guide and solution blocks.

Optional `key` gives a block an address
(`#unit/content/key`) for definitions, exercise prerequisites and the coverage ledger;
optional `pages` ("11" or "16-27") names the PDF pages of its first source it draws
on; citations open there, and later pages can differ from the printed slide numbers.

| Block | Provide |
| --- | --- |
| text | Paragraphs, numbered `steps` and/or points; never an empty explanation. Paragraphs frame (one or two sentences); a procedure is steps and conditions are points. An item opening with a short `Label: ` shows the label in bold. |
| definition | A `term`, the `statement` and optional `conditions`, placed right after the passage that introduces the term: it appears inside that section as the term above its full-width meaning, with no heading of its own. Give it a `key`. Write `{{term}}` in any later text, in every workspace, to let students open it in place; the build rejects unknown terms. |
| formula | LaTeX without dollar delimiters (JSON-escaped, e.g. `"\\frac{a}{b}"`), a plain-language reading, symbol definitions and conditions. A reusable rule states its domain (\(a^2+b^2 > 0\)) and when to reach for it in its `conditions`. Unsupported macros, links and unsafe markup fail validation. Keep `mathml` only for legacy input; never supply both. |
| derivation | Working the student should be able to redo: `groups` of `lines`, each line one meaningful transformation as LaTeX (a line opening with `=` or another relation continues the line above, and the app aligns the lines on their relation) with a short `reason` saying which rule, substitution or condition makes it follow. When one answer gives several results, give each its own group with a `label` naming the result. Do not split a trivial result into ceremony. Set `walkthrough: true` to step through the lines with Previous and Next (earlier lines stay visible, "Show all steps" reads everything); in a walkthrough a line may carry a `visual` (a table, diagram, plot or figure block) drawing the state that line reaches, such as amplitudes or a vector on the Bloch sphere. Use a walkthrough when several dependent transformations or a changing state are the point; never as decoration. A walkthrough never asks the student to predict: prediction belongs in an exercise step. |
| table | Column labels, rectangular rows and a meaningful caption. |
| code | Language, literal code and an explanation; the app highlights common languages. Label authored examples; never execute downloaded code. Add a `walkthrough` (stops of `lines` such as `"5-6"` and a short `note`) when the reader should follow the code part by part: one idea per stop, at most about six stops. |
| diagram | Nodes placed in lattice cells (`row` and `col`, 0 to 5, one node per cell), optional directed or labelled edges (self-loops and two-way pairs allowed) and frames; arrange them as in [diagrams](diagrams.md). The app sizes, spaces and routes everything. Circles hold up to four characters; use boxes for longer labels. Frames name active, frontier and visited nodes, highlight `edges`, and list up to six `state` rows (label and value, such as a queue or a domain) that the app shows beside the drawing, marking what changed; the caption says why the step happens. `state_labels: caption` omits traversal bookkeeping for concept maps. A single-frame diagram shows only its caption; the description becomes the image's accessible name. |
| uml | `diagram: class` (classes with optional `interface`, `abstract` or `enumeration` stereotype, attributes and operations in UML notation such as `+ update(t: double): void`, `static`/`abstract` flags; relations with kind, label and multiplicities), `diagram: sequence` (participants as objects `name: Type` or actors; ordered call, return, async or create messages, self-calls allowed; loop, alt, opt or par fragments over a message range), `diagram: state` (`states`: `initial` and `final` pseudostates, named states with an optional `entry / ...` activity; `transitions` labelled `event [guard] / action`, self-loops allowed) or `diagram: flowchart` (`steps` of kind `start`, `end`, `action`, `io` or `decision` with short `text`; `flows` between them, every decision exit labelled with its answer). The app lays it out in the order you list elements; write them as in [diagrams](diagrams.md). `start` is the child for inheritance and realization, the whole for aggregation and composition, and the client for directed association and dependency. |
| files | A small project with a `key`, a `description` and `files` (relative `path`, literal `code`, `editable` for files the student changes). The app shows a file tree, tabs and highlighted, numbered code; edits stay in the browser. Use for programming exercises that span several files. |
| tree | An optional `description` only for what the tree does not show (it is readable text, so never restate it) and a `root` entry with a short `label`, an optional `note` (such as a size or a return value), `kind` (`folder` or `file` for a file structure, else the default `item`) and nested `children`. The app draws an indented tree with connector lines. Use for hierarchies: file structures, object trees of a Composite, call or recursion trees. Never encode a hierarchy as a table of parents. |
| figure | A picture of what the idea looks like, for anything with a shape that is not a graph, table or chart: a robot arm with its angles, a grid world, rooms, a circuit, a geometric construction. Give an `alt` text, an optional `caption` and either `svg` or `image`. `svg` is an inline drawing with a `viewBox` 320 to 400 units wide (480 at most) and labels of 16 units (notes 14), drawn as in [figures](figures.md); it may use line, polyline, polygon, path, rect, circle, ellipse, text, tspan, g and defs with markers, and colours only through the classes ink, muted, accent, fill-ink, fill-muted, fill-accent, fill-surface and fill-canvas (plus dashed, thin, thick, small, bold). Scripts, links, styles and fixed colours fail the build. `image` names a PNG, JPEG or WebP under 2 MB in the app's `figures/` folder, such as a picture you generated or one taken from the course material. |
| plot | A description, short Unicode axis labels, increasing finite bounds and up to five labelled series, each with data `points` or a `function` of x that the build samples; a series `style` (`line`, `markers`, `points`, `steps`, `stems`), optional `values`, shaded `areas`, marked `notes`, `x_ticks`/`y_ticks`, `y_scale: log` and `legend: direct`, chosen as in [plots](plots.md). The app lists data series in a table. Use source-backed quantities, units and sensible scales. |

Flashcards use one objective plus front, back and sources. Questions use an
objective, prompt, level, up to three context `blocks` (a figure, code, diagram, formula,
table, tree, UML or plot block), options with individual feedback, one correct key, an
explanation, an optional `hint` and sources. A question about a concept may stand alone.
A question that needs data shows it in its picture and keeps the prompt to the question;
a one-row table that repeats the prompt is filler. Write four plausible options by
default; the schema sets the accepted range. Every objective needs a question; counts
follow learning needs, not quotas. A unit's optional `lectures` names the Lecture
that cover it.

## Build

Run `tum-mcp study build PROJECT` after a coherent batch. It blocks stale or
conflicted sources and edited generated data. Review source meaning and locators
before rebinding hashes; byte changes alone need not require rewriting valid
teaching. A modified core unit gets a new revision and a fresh progress namespace;
unchanged units keep theirs.

Build preserves and reports customized app files and leaves unknown files untouched.
Do not change renderer code to bypass invalid content.

Launch with `tum-mcp study` inside the project; it opens `127.0.0.1:8765`. Keep the
same address and port so browser progress remains available, or pass `--port PORT`.
For unattended checks, `tum-mcp study serve PROJECT --port 0` prints a URL without
opening a browser. The app needs no campus credentials or external services.

Study and Exercises share one app and source inventory; preserve the other workspace
when authoring. New projects use `app/`; existing `study/` projects keep working, and
`study build PROJECT --upgrade-layout` moves them explicitly with a checked backup.
