# Text pass

Read every passage once, at reading speed, in the order the student meets it: lesson,
definitions, captions, questions, options, hints, steps and solutions. This pass scores
Clarity and Cognitive load; the rules come from prepare-study's
[writing guide](../../prepare-study/references/writing.md).

## Procedure

1. Run `tum-mcp study report PROJECT --section quality`. Each flag is a finding until you
   have read the place it points to. `long_section`, `dense_paragraph`,
   `prose_calculation`, `compressed_working`, `plain_math`, `described_object`,
   `meta_reference`, `restated_context` and `dense_statement` are always fixed by
   restructuring, never kept. `dense_introduction`, `unexplained_identity` and
   `tall_inline_math` are read first: fix them unless the passage already orients the
   reader and unpacks its notation, or the object reads well inline.
2. **Walk it as a first encounter.** Before judging sentences, read the item once as a
   student who knows only what earlier sections and units taught (the course map's
   `builds_on`) and may have forgotten a definition from weeks ago. Keep a ledger, section
   by section, in reading order:

   | Section | Known so far | New terms | New symbols | Jumps | Likely sticking point |
   | --- | --- | --- | --- | --- | --- |

   A jump is a line or step whose result the student cannot get from the one before. The
   ledger finds where the student must absorb too much at once, recall something taught far
   back, guess a missing step or face a harder task too soon. For an exercise, run it across
   the statement, each guide step and Compare. Each finding names the passage and its effect
   on that student (`cognitive_load.first_encounter`, `cognitive_load.reminder_at_use`).
   A reader who needs more time is not a weaker student; do not describe them as one.
3. After each paragraph, say its one idea in a sentence. A paragraph with two ideas, or
   none, is a finding.
4. Count what the student must hold at once: new terms, symbols, cases and earlier
   results. More than one new idea per section or step is a finding.
5. For every notation-heavy statement, check that it is unpacked where it is used
   (`clarity.notation_unpacked`): the claim in words, a one-line reminder of what each
   symbol means here, the worked case, then the identity with its conditions. Open the
   rendered page too: odd spacing or a broken symbol is a render finding, not a reason to
   rewrite correct content.
6. Check that each term is defined where it first appears and linked as `{{term}}` later;
   that every symbol is set as mathematics; that a procedure is numbered steps and a
   worked calculation shows one value per step.
7. Check every object the text names: a matrix, vector, table, graph or state is shown,
   not described by its entries (`representation.shown_not_described`, scored in the
   visuals pass). Then check every caption and question: a caption states the point of
   its picture; a question asks one thing and fits one phone screen. What a passage, caption or prompt
   repeats is scored in the [structure pass](structure.md).
8. Mark lines that talk about the material ("The lecture groups…", "Authored example")
   or tell the student to work or compare; they teach nothing.

## Findings

Quote the start of the passage and say what the student meets: "`block:2` 'A heuristic is
admissible…' gives the definition, its consequence and an example in one 70-word
paragraph."
