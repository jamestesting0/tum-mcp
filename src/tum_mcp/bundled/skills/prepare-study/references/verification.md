# Verification scope

Check what the change can affect, in the generated app rather than mock HTML.
Reuse evidence while its inputs are unchanged; fewer checks must not mean weaker
evidence or unreviewed teaching. A schema pass or build never verifies subject matter.

## Cheap gates first

Review new or changed teaching with [teaching](teaching.md) and [practice](practice.md),
then run `tum-mcp study build PROJECT`. Resolve stale source dependencies. If build
reports preserved custom app files, confirm they support the new content before
relying on them.

## Select checks

| Change | Check |
| --- | --- |
| New site | Prove one demanding unit, then confirm every unit's Content, Flashcards and Practice render with their sources and without script errors. Walk the student path below once. |
| Content edit | Rebuild, run `tum-mcp study visuals PROJECT --unit KEY` and fix what it reports, then open the changed view. Read the rendered text and notation, and the contact sheets of its tables, diagrams and plots, at a phone width (~390px) and a desktop width. |
| Unit order, labels, paths or citations | Outline grouping, home topic rows, Next links and Revision order; these can change without unit revisions changing. |
| Inventory-only update | Staleness and coverage reporting; rebuild affected units, not unchanged teaching. |
| Skill prose | Links, metadata and instructions; not unrelated application suites. |

Independently work every new or changed question, card and trace: verify the key,
each option's feedback, the assumptions and the example against the source. Repeating
generic clicks for every question proves less than reviewing each item's meaning.

## Student path

On a new site, follow the path a student takes on a phone and on a desktop: home →
Start → Content → Next → rate cards → Practice → check answers to End of set → next
unit → Revision. Note any text that does not fit, notation that breaks, or a step
that needs an extra scroll or tap, and fix the content that causes it. App behavior
itself is covered by the package's tests; report a suspected app defect instead of
changing the installed files.

## Evidence

Use a real browser with a task-owned profile and no campus cookies, such as
Playwright Chromium or system WebKit. Derive expectations from the content and
semantic roles, not guessed headings or sleeps. Inspect the first useful error
before retrying; do not reinstall browsers or frameworks to repair a locator.

Keep a short private record of tested unit revisions, cases and results. Stop only
processes you started. Honor required project gates. Report unrun checks and gaps
honestly; neither a build nor testing certifies bug-free software.
