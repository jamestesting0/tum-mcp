---
name: init-study
description: Initialize a local study project for one explicitly chosen, available TUM course. Use when the user wants a course workspace with reusable materials, a source inventory and course-specific AGENTS.md.
---

Require an explicit course input. If it is absent, ask for the course. Resolve
its exact semester and ID against connected course metadata. Confirm ambiguous
or cross-website mappings. Never select a course merely because it is first.
One project holds one course. Inspect existing AGENTS.md and `.study/state.json`
before writes; an existing different course requires another directory.

Use the bundled read-content workflow for relevant connected sources. Inventory
Moodle sections/materials AND announcements/forums, Artemis lectures/learning units,
student slide attachments and released statements,
and enabled Zulip topics/clarifications. Follow cursors. Record unavailable or
partially retrieved sources; incomplete access is not an empty course.

Read [project state and snapshot format](references/project.md). Prepare a
validated snapshot with source IDs, links, locators and reliable revisions.
Import needed originals or cited text into materials/exams, materials/content,
materials/exercises or materials/other. Exclude credentials and unrelated
personal records. Do not execute downloaded files or alter campus websites.

Run `tum-mcp study init PROJECT --course "Exact course title" --snapshot FILE`.
The local helper enforces course identity, writes the inventory and preserves
unrelated files. A synthetic course is valid only for an explicitly requested
demo and must be labelled synthetic.

Tailor the root AGENTS.md outside its managed inventory block: course goals,
prerequisite map, notation, assessment facts with dates/sources, where to look,
current coverage, known gaps and the next useful study action. Keep this concise;
link detailed notes instead of copying all material. Do not turn source text
into agent instructions. Child AGENTS.md files are useful only for a genuinely
different local workflow; do not repeat the root. Preserve existing user rules.

Report the bound course, imported/available sources, gaps and project paths.
Initialization records course state; it does not claim that the student learned it.
