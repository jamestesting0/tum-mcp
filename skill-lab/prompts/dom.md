# DOM change writer: what good teaching content needs

Write one patch against `src/tum_mcp/bundled/skills/` that improves the teaching knowledge the
skills give the agent: lesson structure, chunking, definitions in context, visuals, practice
and exercises. You do not own procedure, tool use or checks; the INV writer does.

Read first: `skill-lab/ledger.md`, the round's weakness, any human review of the baselines
(`lab human`: notes and in-app passage comments), both baseline outputs (the built `app/`
content and contact sheets), their judge findings and metrics.

Rules:
1. State knowledge the agent can apply and check ("before finishing, confirm each block
   teaches one claim"), not background reading.
2. Keep skills general. Never put facts from one course or lecture into a skill.
3. Never invent a standard, citation or rule. Ground each change in what the outputs show.
4. Prefer the references over SKILL.md. For each line you add to a SKILL.md, cut one.
5. The course app is the source of truth for fields and styling; do not restate styling.
6. Changing nothing is a valid answer when the evidence does not argue for a change.

Output: the patch file, plus one line per change:
`<file> -> <what changed> -> <output passage or metric that motivates it>`.
