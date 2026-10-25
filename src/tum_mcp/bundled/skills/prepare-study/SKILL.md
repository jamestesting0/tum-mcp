---
name: prepare-study
description: Create or extend a local interactive study website from one initialized TUM course project. Use for source-backed explanations, formulas, diagrams, flashcards and practice questions in study/.
---

Require `.study/state.json` and read the course AGENTS.md. If missing, use init-study
with an explicit course input first. Inspect an existing study/ before changes.
Compare its source revisions with current project state. Reuse unchanged units;
regenerate only units whose learning content or dependencies changed. Report
missing/outdated material instead of claiming complete coverage.

Before generating a unit, read the relevant local sources and their locators.
Choose lectures/weeks when the course uses a clear sequence, otherwise choose
topics. Use one convention consistently. There is one course per project; the
sidebar lists units, not unrelated courses.

Load these contracts for the work you are doing:
- [Content and teaching](references/teaching.md): coverage, length, language and assessment quality.
- [Fixed design system](references/design.md): formulas, visuals, tables, navigation and states.
- [Content schema and build](references/content.md): validated data, source revisions, incremental build.

Write `study/content.json` with source-backed units. Each unit has concise content,
active-recall flashcards and critically checked multiple-choice practice. Explain
necessary terms. Use worked examples, equations, diagrams and comparison tables
where they reduce effort; decoration is not an explanation. Apply STE sentence
structure while retaining technical precision, conditions and uncertainty.

Run `tum-mcp study build PROJECT`. The helper validates course/source bindings
and structured content, then installs the reusable local renderer. It preserves
edited templates and unrelated files. Keep learner progress separate from content;
a revised question must not inherit an old correct-answer state.

Run `tum-mcp study serve PROJECT` for a loopback-only preview. Exercise navigation,
formulas, diagram steps, card reveal/rating and wrong/correct question feedback.
Check phone/desktop, dark/light, keyboard and reduced motion. Never publish a
course site or send course data to another service without the user's request.

Report generated/retained units, coverage gaps, checks and the local preview.
Do not claim a question bank is an official exam, that a score proves mastery,
or that STE-inspired explanations have certified dictionary compliance.
