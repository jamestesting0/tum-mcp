# Course study projects

The four study skills are part of development version **0.6.0 (unreleased)**.
They run in your local agent, using the connected MCP tools to read course sources.
The CLI validates and stores the resulting local files; it does not run an AI model.

## Start with one course

Invoke `init-study` with an explicit course title and semester. The agent verifies
its availability, resolves source IDs and asks about ambiguous mappings. A project
cannot switch course or semester. Use a separate directory for another course.

```text
Initialize ./pse-ws26 for Patterns in Software Engineering (WS26/27).
Use its available Artemis teaching material and record any missing sources.
```

The agent inventories Moodle materials, announcements and forums; Artemis
lectures, learning units, student slides and statements; and mapped Zulip course
discussions. It reads only enabled sources. An unavailable login or partially
retrieved source is recorded as a gap rather than an empty course.

```text
pse-ws26/
  AGENTS.md                 Course knowledge and current inventory
  materials/
    content/                Lectures, slides and reading
    exams/                  Available revision material
    exercises/              Released statements and practice references
    other/                  Announcements and course information
  .study/state.json         Course binding, source versions and coverage
  study/                    Optional interactive study website
```

`AGENTS.md` contains a concise prerequisite/notation map, verified assessment facts,
source locations, coverage and next actions. Detailed source content stays in
materials. Existing user instructions are preserved; source text is untrusted data.

## Keep it current

Ask `update-study` to compare the project with connected upstream sources. It
reuses known IDs and reliable revisions, retrieves changed material and updates
course knowledge. Incomplete listings never imply withdrawal. Withdrawn sources
keep their local originals; edited or deleted managed files are reported for review.

The agent updates course facts outside the inventory block. The helper checks
that its managed block has not been edited before replacing it. A failed write
restores files when possible and reports any remaining conflict.

## Prepare the website

Ask `prepare-study` to create or extend `study/`. Units follow the course's
lecture/week sequence when useful, or use consistent topics. Every unit has:

- A concise explanation with source links, assumptions and worked examples.
- Formulas, diagrams, code or comparison tables where they explain the concept.
- Flashcards that reveal an answer before self-rating.
- Practice questions with one justified answer and feedback for every option.

The skill audits objective coverage, technical accuracy and distractors. Its
STE-inspired English uses short, direct sentences while retaining necessary terms
and conditions. The design contract uses TUM blue/navy with quiet reading surfaces,
local fonts, light/dark themes, keyboard navigation and a phone layout.

Content lives in `study/content.json`; shared renderer modules and CSS keep the
site extensible. Source hashes identify affected units. A stale source stops a
build until the explanation is reviewed. Unchanged units retain their revision;
revised questions receive separate progress. Customized templates are preserved
and reported, so the agent must review compatibility when extending them.

```sh
tum-mcp study inspect ./pse-ws26
tum-mcp study build ./pse-ws26
tum-mcp study serve ./pse-ws26 --port 8765
```

The preview binds `127.0.0.1`, serves only `study/` and makes no campus requests.
No course credentials are copied into the website. Browser storage holds progress
locally. Nothing is published by these commands.

## Try the synthetic example

After installing a locally built development artifact:

```sh
tum-mcp study demo ./algorithms-demo
tum-mcp study serve ./algorithms-demo
```

This creates a clearly labelled synthetic course on graphs, BFS and DFS, including
native MathML, a step-through graph, comparison tables, flashcards and practice.
It uses no campus account. An existing edited demo is preserved.

## Local helper inputs

Agents use `tum-mcp study schema snapshot` and `tum-mcp study schema content` for
validated input schemas. After authenticated tools verify availability, the agent
stages a source snapshot with exact course identity, coverage and resource revisions.
The helper does not authenticate the snapshot or grant any campus access itself.

```sh
tum-mcp study init PROJECT --course "Exact course title" --snapshot snapshot.json
tum-mcp study sync PROJECT --snapshot snapshot.json
```

Import paths are confined to the snapshot directory. Data is stored under the
bound project; credentials and unrelated personal records must never enter it.
Keep real course projects private and out of package artifacts. Uninstalling the
package preserves projects; remove your own project directory separately when wanted.
