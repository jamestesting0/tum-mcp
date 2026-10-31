# Structure pass

Read the item as an outline first, then compare its parts with each other. This pass
scores Organization and Redundancy; the rules come from prepare-study's
[lesson shape](../../prepare-study/references/teaching.md#lesson-shape) and
[headings](../../prepare-study/references/content.md#blocks).

## Procedure

1. Run `tum-mcp study report PROJECT --section structure`. Each flag on this item
   (`forward_term`, `source_order`, `flat_sections`, `duplicate_title`, `near_duplicate_passage`,
   `near_duplicate_practice`), and `restated_context` from `--section quality`, is a
   finding until you have read the place it points to. `source_order` marks a section
   that returns to much earlier source pages: usually one appended after the lesson was
   written, away from the section it extends.
2. Read only the Contents list: the titles and their levels. Predict what each section
   teaches. A title that does not let you predict it, two titles that sound alike, or a
   level that does not nest is a finding.
   Also check the relationships: a worked case, counterexample or derivation should sit
   below the topic it explains rather than pretending to be its peer. `flat_sections`
   asks for that review on long all-level-1 outlines; parallel topics may legitimately
   remain flat. Never fix it by mechanically indenting every second heading.
3. Read the sections in order. For each, note what it uses: terms, symbols, results and
   earlier examples. Anything used before the section or unit that teaches it is a
   finding, even when the term is not marked.
4. Check that each section extends the one before, in the lesson shape: the problem, a
   concrete case, the rule, the procedure, a worked example, the pitfall, the recap. A
   pitfall before its method, a definition far from the passage that needs it, or a
   recap in the middle is a finding.
5. Exercises: the parts appear in the original order, every step names its `part`, and
   each part's steps build on each other. A step may restate the one given it uses, so it
   can be read without scrolling back; restating every given in every step is a finding.
6. Lay each passage beside the picture, table or formula it refers to. Text that
   restates what the picture shows, instead of saying why or what to look at, is a
   finding; so is a caption that lists the picture's content instead of its point.
7. Compare the cards and questions of the item with each other: two that ask the same
   decision in the same form are a finding. A recap of two to four points and a card
   that retrieves a lesson's idea are not.
8. Look for repeated labels: a citation in the text, an assumption stated twice in the
   same place, an instruction the app already gives.
9. Separate reinforcement from duplication before you score a repeat. Ask what the repeat
   does for a student meeting the page for the first time:
   - **Keep** a one-line reminder of a prerequisite where it is used, a recap in different
     words before a hard step, a second example or non-example, or a revisit that takes the
     idea further. It is short and points to the idea's home.
   - **Fix** a passage that explains the same idea in full again, two adjacent passages in
     the same form, or text that restates its picture.
   Name what the repeat costs or gives: "`block:7` re-derives the conjugate trick from
   `block:2` in full; replace it with one line and a link" versus "`block:7` reminds the
   student that \(z^*z = |z|^2\) before using it: reinforcement, keep". The
   [structure gallery](structure-gallery.md) has calibrated cases of both.

## Findings

Name the sections and what repeats or comes too early: "`block:6` 'Why it terminates'
uses the visited set, which `block:8` introduces; move the argument after it."

Explore should hold coherent, independent context without duplicating Content.
Inspect its headings and visuals separately. Its diagrams, definitions and length do
not satisfy core teaching/trace requirements; flag required concepts displaced there.
See [Explore](../../prepare-study/references/explore.md).
