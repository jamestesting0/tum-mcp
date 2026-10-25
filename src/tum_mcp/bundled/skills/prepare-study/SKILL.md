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
- [Verification and known failure modes](references/verification.md): required regressions, evidence and checks scaled to the change.

Reuse the bundled renderer and approved design. Prove one representative unit
before generating a full course: cover the hardest formats it actually needs.
Fix shared behavior there, then populate the remaining units. Do not
repeat design research or add a framework to recreate existing components.

Write `study/content.json` with source-backed units. Each unit has concise content,
active-recall flashcards and critically checked multiple-choice practice. Explain
necessary terms. Use worked examples, equations, diagrams and comparison tables
where they reduce effort; decoration is not an explanation. Apply STE sentence
structure while retaining technical precision, conditions and uncertainty.

Run `tum-mcp study build PROJECT`. The helper validates course/source bindings
and structured content, then installs the reusable local renderer. It preserves
edited templates and unrelated files. Keep learner progress separate from content;
a revised question must not inherit an old correct-answer state.

Read the verification guide before the first preview. Run `tum-mcp study serve
PROJECT` and verify the actual generated app in a real browser. Check all new
content for correctness; exercise shared interactions with representative cases.
Reuse passing evidence for unchanged renderer/content revisions. After an edit,
rerun affected checks and a sibling regression; broaden for shared changes.
Never publish a course site or send its data elsewhere without the user's request.

Report generated/retained units, coverage gaps, verified revision, checks actually
run, unresolved issues and the local preview. A screenshot count or successful
build is not proof of working interactions. Do not claim a site is bug-free.
Do not claim a question bank is an official exam, that a score proves mastery,
or that STE-inspired explanations have certified dictionary compliance.
