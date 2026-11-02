# Cheatsheet and semester map

The cheatsheet is what a student rereads in the last days: everything that earns points,
each in one line. That is facts, definitions, rules, lists, classifications, comparisons,
code and frameworks as much as formulas and methods. Lecture content that is good to
know but not exam-relevant stays in Study. Record deliberate exclusions in
`.tum-mcp/notes/exam-exclusions.md`.

## Inventory first

Before writing entries, read every source in the exam's scope (slides, scripts, sheets,
stated exam guidance, past questions) and record what each makes exam-relevant as `exam`
requirements in the [coverage ledger](../../prepare-study/references/coverage.md): a key,
the requirement, its locator, a status and the entries that hold it. Past questions show
what was asked, not all that can be: a request limited to one past exam or to some
topics still reads the lecture material that teaches them. Every current content source
gets requirements or one `out_of_scope` requirement saying why; until then the report's
`unrecorded_sources` fails the sheet's coverage. Map every requirement to an entry or a coherent group
of entries; one entry may hold several. Then compare the sheet with the inventory, not with
its own entry list: `study report PROJECT --section coverage` lists `cheatsheet` gaps,
unrecorded sources and entries no requirement asks for.
Blocks follow the Study [heading rules](../../prepare-study/references/content.md#blocks):
an untitled block continues the entry above it.

## Choose entries

Every concept states its basis, and code checks it against the registry:

| Basis | Meaning |
| --- | --- |
| `tested` | A current or partial past question tests it. |
| `prerequisite` | It links (`requires` or `derives`) towards a tested concept. |
| `emphasized` | The course explicitly marks it exam-relevant; cite that source. |
| `untested_core` | Central to the course but absent from past exams; these feed forecasts. |

Use tier `core` for what every student must know and `supporting` for the rest. A
`distinction` or `pitfall` entry is worth its place when students confuse two ideas.

## Write compactly

- **line** (about 240 characters): the fact, rule or definition itself, with its key
  condition. Readable without opening the entry.
- **formula**: LaTeX with plain-text reading, symbols and conditions; `symbols` lists every
  variable with its general meaning, shown when the entry opens
  ([variable meanings](../../prepare-study/references/variables.md)); the line says when
  it applies.
- **trigger**: the question feature that should bring this entry to mind.
- **pitfall**: the one mistake that costs points.
- **details** (behind Expand): the reference itself in the form its retrieval task needs
  (table below), and conditions, exceptions or a mini example where they help. Never put
  essential conditions only in details. Detail titles take levels 1 to 3.
- **workflow_from**: for a `procedure` or `algorithm` whose method is an Exam pattern's
  workflow, name that pattern; the entry shows its steps and links to its practice. Other
  patterns that list the concept appear as links only. A method without details or
  `workflow_from` is flagged by `exam-report`.
- **symbols**: on an entry without a formula whose line, tables or text use variables, each
  variable with its general meaning, listed when the entry opens. Never type that list as a
  sentence.
- **path**: one or two section labels inside the topic ("Linear structures"), so related
  references sit together. Group by subject, never by form ("Formulas", "Code").

A complete one-line fact needs no details: the app shows it without a disclosure. Do not
pad an entry to give it something to open.

| What the student retrieves | Form |
| --- | --- |
| A definition or fact | The line; an example or exception only when it helps |
| A rule, theorem or equivalence | Claim with its hypotheses, direction and exceptions |
| Members, properties or obligations | A list (`points`, or `steps` when order matters) |
| A comparison or lookup | A `table` with labelled axes, conditions and units |
| A rule with two inputs | A `table` as a matrix: one input per axis |
| A classification | A `tree`, or a grouped list |
| A formula | `formula` with its meanings and conditions |
| Syntax, an API or a configuration | A short `code` block, read-only |
| Code structure | A class skeleton, `uml`, a `tree` of files or a small `files` block |
| A shape, a state or a spatial relation | A `diagram`, `figure` or `plot` |
| A method | Steps with what each applies, or `workflow_from` |
| A framework or case reasoning | Its parts and distinctions, then the principle a case shows |

The table guides the choice; it is not a quota. Keep one coherent reference in one entry
(a whole access-modifier table), and split an entry that mixes unrelated retrieval tasks.

Use the course's notation and language, set as in
[notation](../../prepare-study/references/content.md#notation). Each fact appears once; link instead of
repeating it in another entry. When Study exists, every concept names in `units` the
units that teach it; its line and details compress that lesson, never copy it. When one
Study block teaches the concept, name it in `passages` (`unit` and `block`): the Recall row
on patterns and solutions opens that passage beside the page.

## Draw the map

Links run from a foundation (`start`) to what builds on it (`end`): `requires` for
prerequisite knowledge, `derives` when one result follows from another, `contrasts`
for ideas students confuse. Prerequisite and derivation links must not form a cycle.
Draw only links a student benefits from seeing. Put the core ideas on the map
(`on_map`) and leave supporting detail off when the map would get crowded; around 60
to 80 nodes stay readable. Topics are the map's columns in course order.

Study Explore is not evidence for an exam requirement and cannot supply core unit
links. If an actual task requires an optional-only concept, record the dependency and
repair core Study teaching when authorized. Keep this separate from Exam's own
`supporting` tier; see [Explore](../../prepare-study/references/explore.md).
