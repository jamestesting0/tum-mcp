# Writing for learners

Shared by prepare-study, prepare-exercises, prepare-exams and review-course. The student
reads to learn the idea. Every sentence teaches something about the subject; a sentence
that only talks about the material, the page or the writing is removed.

## Structure before prose

Working memory holds only a few new elements, so a learner studies a procedure one stage at
a time. Prose frames an idea in one or two sentences; everything else is structure.

- **Procedure or algorithm**: one lead sentence saying what it computes, then `steps`, one
  action each, opened by a short label: "Initialize: …", "Back up: …", "Stop: …".
  Conditions and guarantees follow as labelled `points`: "Converges when: …",
  "Approximation: …". The app shows each label in bold.
- **Worked example**: its own section after the procedure. Give the setting first (a
  table, points or a figure), then one computed value per step, labelled with the
  sub-result it reaches:
  "First backup: \(Q(\mathrm{continue}) = 1 + 0.5 \times 3 = 2.5\), below 3."
  End with the conclusion as the last step. Several states over several rounds are a
  table trace instead.
- **Cases, conditions, comparisons**: points or a table, never a sentence joined by
  "and", "while" or "whereas".
- **Calculation the student should redo**: a `derivation` block, one transformation per
  line, each with the reason it follows; separate requested results get labelled groups.
- **An object with a shape** (a matrix, vector, table, graph, state): show it. Text that
  lists its entries ("the diagonal matrix with entries 1, 0", "the graph has edges A–B,
  B–C") makes the student build the picture in their head; write the matrix or draw the
  graph, then say what to notice in it.

Every symbol and formula in that structure is inline LaTeX
([notation](content.md#notation)), so a step reads as one expression instead of typed
characters.

## Say the idea, not where it came from

- Do not narrate the source: no "the lecture groups…", "the slides say…", "the course
  focuses on…", "this section explains…". The citation carries the source and the heading
  names the topic. State the idea itself: "AI approaches differ in two ways: …".
- Do not label examples: no "Authored example:". Give the example; start with "For
  example," only when the switch from rule to case is not obvious.
- Do not point at the layout: no "In the table…", "As the diagram shows…". Put the fact in
  the sentence, or let the picture carry it alone.
- Name whose convention it is only when sources differ, for example the moment a search
  tests for the goal.

## Simplified Technical English

These rules follow ASD-STE100, adapted for teaching:

- One idea per sentence. Keep a step or instruction under 20 words and a description
  under 25.
- One topic per paragraph, at most two sentences (see above).
- Use the active voice and the present tense, with the actor first: "A* expands the
  node", not "The node is expanded".
- Use one term for one concept. When the frontier is "the frontier", it never becomes
  "the open list" or "the queue" two sentences later.
- Use common words. Define a technical term once, then use it exactly as defined.
- Repeat the noun when "it" or "this" could mean two things.
- Keep articles and short words; do not compress sentences into telegraph style.
- In an instruction, give the condition first and start the action with the verb.

## Remove AI patterns

Cut or rewrite:

- Openers, signposts and wrap-ups: "In essence", "It is important to note that",
  "Moreover", "Overall", a closing sentence that restates the paragraph.
- Stacked hedges ("can potentially") and hollow intensifiers ("truly", "genuinely").
- Inflated words: leverage, robust, comprehensive, seamless, crucial, pivotal, delve.
  Write "use", "reliable", "complete".
- "Not X, but Y" reveals and groups of three added for rhythm.
- "Serves as" (write "is"), "in order to" (write "to") and em dashes (use a full stop or
  a comma).

## Check

Read each passage once as the student would. Remove every sentence the student does not
need, and split every sentence they would read twice. Then run `tum-mcp study report
PROJECT` and restructure, never justify, what it flags: `dense_paragraph` (a paragraph
over 45 words, or three sentences over 30), `prose_calculation` and `compressed_working`
(calculations chained in a sentence), `plain_math` (mathematics typed as characters),
`described_object` (an object spelled out instead of shown) and `meta_reference`
(narration of the source).

## Sources

The structure rules come from learning research as packaged in open teaching skills:
[education-agent-skills](https://github.com/GarethManning/education-agent-skills) (worked
examples and explicit instruction: Sweller, Renkl, Rosenshine's "small steps") and
[id-skills-for-claude](https://github.com/trinarimmer-stack/id-skills-for-claude)
(chunking, signalling, worked-example annotation). Step labels follow subgoal labelling
(Catrambone): naming each stage helps the learner transfer the procedure. Not adopted:
classroom scripts, think-alouds, audio narration and interactive fading, which need a
teacher or features the app deliberately leaves out.
