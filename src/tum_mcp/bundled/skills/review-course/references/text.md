# Text pass

Read every passage once, at reading speed, in the order the student meets it: lesson,
definitions, captions, questions, options, hints, steps and solutions. This pass scores
Clarity and Cognitive load; the rules come from prepare-study's
[writing guide](../../prepare-study/references/writing.md).

## Procedure

1. Run `tum-mcp study report PROJECT --section quality`. Each flag is a finding until you
   have read the place it points to. `long_section`, `dense_paragraph`,
   `prose_calculation`, `plain_math`, `meta_reference`, `restated_context` and
   `dense_statement` are always fixed by restructuring, never kept.
2. After each paragraph, say its one idea in a sentence. A paragraph with two ideas, or
   none, is a finding.
3. Count what the student must hold at once: new terms, symbols, cases and earlier
   results. More than one new idea per section or step is a finding.
4. Check that each term is defined where it first appears and linked as `{{term}}` later;
   that every symbol is set as mathematics; that a procedure is numbered steps and a
   worked calculation shows one value per step.
5. Check every caption and question: a caption states the point of its picture; a
   question asks one thing, fits one phone screen and repeats nothing its picture shows.
6. Mark lines that talk about the material ("The lecture groups…", "Authored example")
   or tell the student to work or compare; they teach nothing.

## Findings

Quote the start of the passage and say what the student meets: "`block:2` 'A heuristic is
admissible…' gives the definition, its consequence and an example in one 70-word
paragraph."
