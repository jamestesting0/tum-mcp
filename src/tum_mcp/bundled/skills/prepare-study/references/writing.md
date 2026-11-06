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
  `walkthrough`, each step with its reason ([representations](representations.md#algorithm-traces)).
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

## Let each sentence follow from the last

A first-time reader should never have to reach the end of a sentence or section to make
sense of its start (cohesion):

- **Familiar before new.** Start a sentence with what the reader already has (the topic,
  the result just reached, the term the last sentence ended on) and end with what is new:
  "Each iteration rotates the state by \(\theta\). This rotation moves amplitude towards
  the marked records", not "Towards the marked records, amplitude is moved by the rotation
  each iteration applies".
- **Point first.** A paragraph or block opens with its point and the rest supports it;
  the first sentences of a section alone tell its argument.
- **Say how ideas relate** where a first-time reader could not infer it: the limitation the
  next idea removes, the idea it contrasts with, what follows from it. "Scoring every hidden
  path takes \(2^T\) terms, so filtering keeps one belief and updates it."
- **Connect only where the logic turns.** "So", "but" and "because" carry a real relation;
  stacked "Moreover" or "Furthermore" fake one. A sentence about the page ("This section
  explains filtering") or a bridge between parallel cases teaches nothing; join parallel
  cases with a table or one framing line.
- **One term, one referent** (see Simplified Technical English below).

Exam text has been studied first: hold it to consistent terms and no unexplained jump, and
do not add linking sentences there. Cohesive text helps readers new to a topic most, while
readers who know it learn as well or better from compact text.

## Cut what the reader already has

The same information in a second form, or words that add nothing new, take attention away
from what is new and lower learning (redundancy and coherence principles). Cut a word,
phrase or sentence when the reader already has it:

- It repeats what sits beside it: the heading, a label, the figure, the table or the list
  below. A heading "Not prepared yet" needs no sentence saying the sheets are not prepared.
- It states what the reader will plainly see or do: "choose one below", "as shown
  above", "note that", "the answer is given in the solution".
- It qualifies a label that the place already explains: "Full solution" beside a
  question is "Solution"; "Overview of filtering" is "Filtering".

Short is not the goal; nothing missing is. Keep, or add, the words that supply a link
the reader cannot make alone: a definition, a reason, a relation or a condition. Rewrites
that add such links help understanding at least as much as rewrites that only shorten,
and shortening that deletes them hurts. What counts as known depends on the reader: a
one-line reminder that a first-time Study reader needs is redundant in Exam, where the
student has studied the idea.

## Simplified Technical English

These rules follow ASD-STE100, adapted for teaching:

- One idea per sentence. Keep a step or instruction under 20 words and a description
  under 25.
- One topic per paragraph, at most two sentences (see above).
- Use the active voice and the present tense, with the actor first: "A* expands the
  node", not "The node is expanded".
- Use the verb, not a noun made from it: "compute the trace", not "perform the
  computation of the trace"; "if the matrix is unitary", not "given the unitarity of the
  matrix".
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

## Fix the passage, not the sentence

A review finding is fixed by rewriting the passage it sits in until it reads straight
through, never by splicing a sentence in front of it. A spliced opening that leaves the
reader to sort out "these", "respectively" or "the former" is a new defect; a checker
verifies a fix by quoting the rewritten passage.

## Check

Read each passage once as the student would. Remove every sentence the student does not
need, and split every sentence they would read twice. Then run `tum-mcp study report
PROJECT` and restructure, never justify, what it flags: `dense_paragraph` (a paragraph
over 45 words, or three sentences over 30), `prose_calculation` and `compressed_working`
(calculations chained in a sentence), `plain_math` (mathematics typed as characters or read aloud in words, "theta over two"),
`described_object` (an object spelled out instead of shown), `listed_derivation_line`
(several statements in one derivation line), `unaligned_line` (a derivation line without a
relation), `unexplained_symbol`, `generic_meaning`, `renamed_meaning` and `echoed_meaning`
([variable meanings](variables.md)), `typed_math_label` (a figure label typing mathematics),
`nominalisation` ("perform the computation of") and `meta_reference` (narration of the
source).

## Sources

The structure rules come from learning research as packaged in open teaching skills:
[education-agent-skills](https://github.com/GarethManning/education-agent-skills) (worked
examples and explicit instruction: Sweller, Renkl, Rosenshine's "small steps") and
[id-skills-for-claude](https://github.com/trinarimmer-stack/id-skills-for-claude)
(chunking, signalling, worked-example annotation). Step labels follow subgoal labelling
(Catrambone): naming each stage helps the learner transfer the procedure. The redundancy
and coherence rules come from Kalyuga and Sweller, "The Redundancy Principle in
Multimedia Learning" (Cambridge Handbook of Multimedia Learning, 2nd ed., 2014) and Mayer,
*Multimedia Learning* (3rd ed., 2021); a 2022 review in *Smart Learning Environments*
counts coherence and redundancy among the best-studied principles. Their effects shrink
for readers with prior knowledge (the expertise reversal effect), hence the Study and Exam
difference. Familiar-before-new and point-first come from Gopen and Swan, "The Science of Scientific
Writing" (American Scientist, 1990) and Williams and Bizup, *Style: Lessons in Clarity and
Grace*. The Study and Exam difference in cohesion follows McNamara et al., "Are good texts
always better?" (Cognition and Instruction, 1996) and O'Reilly and McNamara (Discourse
Processes, 2007): cohesive text helps low-knowledge readers; high-knowledge readers can learn
from texts with gaps. Keeping the links follows the simplification-versus-elaboration studies (Oh,
TESOL Quarterly, 2001; Srikanth and Li, EMNLP 2023 on elaborative simplification). Not adopted:
classroom scripts, think-alouds, audio narration and interactive fading, which need a
teacher or features the app deliberately leaves out.
