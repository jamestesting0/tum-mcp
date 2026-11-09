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
  condition. Readable without opening the entry. A definition is the course's fullest,
  exam-ready form with every condition, even when a later lecture states it
  (`definition_refined` names it); never the informal first gloss.
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

A complete one-line fact needs no padded details. Related links and citations stay
inside its expansion; the closed row shows only the title, claim/formula and status.

Use three depths of recall: the closed `line` states the short claim or recognition
cue with any essential applicability condition; opening it gives a compact rule,
conditions, meaningful steps or a likely mistake; its links lead to the complete
prepared Study passage and related practice. A method's title plus a slogan and
links is incomplete. Use `details`, formula conditions, `trigger` and `pitfall`, or
reuse a short `workflow_from`; a long workflow is better summarized in details
with its complete practice linked. Keep the expansion useful without copying a
whole lesson. Populate `passages` for the precise taught block when one exists,
and name the patterns that supply its practice. Do not invent a Study link for
material outside the requested preparation scope.
When a prepared weekly exercise actually trains this entry, add its precise
`exercises` reference (`set` and `exercise`). The build checks these links; a shared
lecture topic alone is not enough to claim that an exercise practises the concept.

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
on patterns and solutions opens that passage beside the page. When Exercises exist, list in
`exercises` the problems that practise the concept; those exercises then recall the entry and
its patterns. `tum-mcp study links PROJECT` lists every entry and exercise still without a
link and records a reason when none fits; readiness waits for every decision.

Revision support does not authorize expanding a narrowly scoped Study lesson. If the
sheet needs methods the requested lesson does not teach, record that gap. When the
request allows teaching them, give them coherent teaching, worked instances and a
matching plan before adding retrieval prompts. A paragraph of new algorithm summaries
followed by cards is not a substitute for lessons.

Keep comparison cells short; put shared assumptions and longer exceptions beside the
table, not repeated inside each cell. When phone review is requested, check the expanded
table there too: a cell wrapping into a screenful is not a usable lookup.

## Draw the map

Links run from a foundation (`start`) to what builds on it (`end`): `requires` for
prerequisite knowledge, `derives` when one result follows from another, `contrasts`
for ideas students confuse. Prerequisite and derivation links must not form a cycle.
Every cheatsheet has a semester map, and readiness waits for it (`unlinked_map`): each
idea on the map links at least one other, so the student sees what to learn first and
what follows. Draw only links a student benefits from seeing. Put the core ideas on the
map (`on_map`) and set `on_map: false` for supporting detail with no link worth drawing;
around 60 to 80 nodes stay readable. Topics are the map's columns in course order.

Study Explore is not evidence for an exam requirement and cannot supply core unit
links. If an actual task requires an optional-only concept, record the dependency and
repair core Study teaching when authorized. Keep this separate from Exam's own
`supporting` tier; see [Explore](../../prepare-study/references/explore.md).
