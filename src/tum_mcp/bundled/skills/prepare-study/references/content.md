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
For a single course, use no `path` or one category label (for example `["W00"]`)
followed by the topics. Do not add a course-name folder inside its own site. The
schema accepts deeper paths for legacy sites; flatten needless nesting when
revising, and keep existing unit labels and keys so progress survives. Moving
folders never changes progress.

## Notation

Use `\( ... \)` for variables and short expressions in teaching text: paragraphs,
objectives, table cells, symbol definitions, card faces, question options and
feedback. JSON escapes the backslashes: `"Use \\(v_i\\)."`. Build validates and
compiles them locally to MathML. Convert complete mathematical tokens, never letters
inside ordinary words, and reread the prose after notation edits. Long equations
belong in formula blocks. Keep source titles, outline labels and diagram labels
plain. Dollar signs stay literal; code blocks and comments never interpret markup.

Wrap identifiers, method names, short expressions in code and file names in single
backticks in the same teaching text: `` `getChildren()` `` renders as inline code in
every workspace. Text inside backticks stays literal, including `\(`. Use a code
block for anything longer than one line.

## Blocks

Every block has a title and sources.

| Block | Provide |
| --- | --- |
| text | Paragraphs and/or points; never an empty explanation. |
| formula | LaTeX without dollar delimiters (JSON-escaped, e.g. `"\\frac{a}{b}"`), a plain-language reading, symbol definitions and conditions. Unsupported macros, links and unsafe markup fail validation. Keep `mathml` only for legacy input; never supply both. |
| table | Column labels, rectangular rows and a meaningful caption. |
| code | Language, literal code and an explanation; the app highlights common languages. Label authored examples; never execute downloaded code. Add a `walkthrough` (stops of `lines` such as `"5-6"` and a short `note`) when the reader should follow the code part by part: one idea per stop, at most about six stops. |
| diagram | Positioned nodes, optional directed or labelled edges and frames on the schema's canvas. Circles hold up to four characters; use boxes for longer labels. Frames name active, frontier and visited nodes; `state_labels: caption` omits traversal bookkeeping for concept maps. |
| uml | `diagram: class` (classes with optional `interface`, `abstract` or `enumeration` stereotype, attributes and operations in UML notation such as `+ update(t: double): void`, `static`/`abstract` flags; relations with kind, label and multiplicities) or `diagram: sequence` (participants as objects `name: Type` or actors; ordered call, return, async or create messages, self-calls allowed; loop, alt, opt or par fragments over a message range). The app lays it out. `start` is the child for inheritance and realization, the whole for aggregation and composition, and the client for directed association and dependency. `diagram: state` has `states` (`initial` and `final` pseudostates, named states with an optional `entry / ...` activity) and `transitions` labelled `event [guard] / action`, self-loops allowed. Use for object-oriented designs, design patterns, interactions and behaviour over events instead of a generic diagram. |
| files | A small project with a `key`, a `description` and `files` (relative `path`, literal `code`, `editable` for files the student changes). The app shows a file tree, tabs and highlighted, numbered code; edits stay in the browser. Use for programming exercises that span several files. |
| tree | An optional `description` only for what the tree does not show (it is readable text, so never restate it) and a `root` entry with a short `label`, an optional `note` (such as a size or a return value), `kind` (`folder` or `file` for a file structure, else the default `item`) and nested `children`. The app draws an indented tree with connector lines. Use for hierarchies: file structures, object trees of a Composite, call or recursion trees. Never encode a hierarchy as a table of parents. |
| plot | A description, short axis labels, increasing finite bounds and series of ordered points inside the axes. The app adds a data table. Use source-backed quantities, units and sensible scales. |

Flashcards use one objective plus front, back and sources. Questions use an
objective, prompt, level, options with individual feedback, one correct key,
an explanation and sources. Write four plausible options by default; the schema
sets the accepted range. Every objective needs a question; counts follow learning
needs, not quotas.

## Build

Run `tum-mcp study build PROJECT` after a coherent batch. It blocks stale or
conflicted sources and edited generated data. Review source meaning and locators
before rebinding hashes; byte changes alone need not require rewriting valid
teaching. A modified unit gets a new revision and a fresh progress namespace;
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
