# Cheatsheet and semester map

The cheatsheet is what a student rereads in the last days: the ideas that earn points,
each in one line. Lecture content that is good to know but not exam-relevant stays in
Study. Record deliberate exclusions in `.tum-mcp/notes/exam-exclusions.md`.

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
- **formula**: LaTeX with plain-text reading, symbols and conditions; the line says when
  it applies.
- **trigger**: the question feature that should bring this entry to mind.
- **pitfall**: the one mistake that costs points.
- **details** (behind Expand): derivation sketch, mini example, edge cases, links to
  Study units. Never put essential conditions only in details.

Use the course's notation and language. Each fact appears once; link instead of
repeating it in another entry.

## Draw the map

Links run from a foundation (`start`) to what builds on it (`end`): `requires` for
prerequisite knowledge, `derives` when one result follows from another, `contrasts`
for ideas students confuse. Prerequisite and derivation links must not form a cycle.
Draw only links a student benefits from seeing. Put the core ideas on the map
(`on_map`) and leave supporting detail off when the map would get crowded; around 60
to 80 nodes stay readable. Topics are the map's columns in course order.
