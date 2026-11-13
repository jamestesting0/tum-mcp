# Scoring rubric

Each dimension scores 1 (blocks learning), 2 (works with friction) or 3 (easy to learn
from). Hunt for failures check by check: each failure is a finding that names its check
(`"check": "redundancy.text_restates_picture"`) and quotes its passage word for word, so the
report can count which checks fail most. A dimension with an accepted finding scores 2, or 1
when the place blocks learning: one wrong answer makes correctness 1 even if the rest is
right. Without one it scores 3.

Items (each unit, exercise and Exam pattern) score ten dimensions; the course scores three:
Optional audio/videos use the separate [media rubric](media.md), not these item
requirements. They do not need interactive practice or a duration target.

Apply the [workspace profile](profiles.md) before these checks. It replaces Study-specific
demands for exercises and defines the evidence for Exam and Lecture course findings. The
unit's plan in `.tum-mcp/plans/` adds its own decisions to these checks. Each 3 quotes its
closest call, the passage that came nearest to failing, under `evidence`.

| Pass | Dimensions |
| --- | --- |
| [Logic](logic.md) | Correctness, Coverage |
| [Text](text.md) | Clarity, Cohesion, Cognitive load |
| [Visuals](visuals.md) | Representation, plus a score per drawn visual |
| [Interaction](interaction.md) | Practice |
| [Intuition](intuition.md) | Intuition |
| [Structure](structure.md) | Organization, Redundancy |
| [Course](course.md) | Course organization, course redundancy, Integration |
| Cheatsheet (`exam/sheet`) | Correctness, Coverage, Clarity, Representation, Organization, Redundancy, with the [Cheatsheet](#cheatsheet) checks only |

## One owner per problem

A problem costs one point, in one dimension. When a symptom could fit two, score it
where this table puts it:

The weakness is one teaching problem counted as several defects.
File each defect once under the owner check from this table. Put other asked checks
the same defect fails in the finding's `also`; the owner alone determines its score.
Separate failures still get separate findings, even when they occur in one passage.

| The student meets | Score it under |
| --- | --- |
| Text, a caption or a question's table that repeats its picture or prompt | Redundancy |
| A term or result used before the page or course teaches it | Organization |
| An exercise without a link to the passage it needs, or a link to the wrong one | Integration (course) |
| An idea with no visible reason for coming where it does; the rule before a needed example | Intuition |
| A section placed far from the one it extends, or appended at the end | Organization |
| A section whose relation to the one before a first-time reader cannot tell | Cohesion |
| A sentence that opens on new information, or a paragraph whose point comes last | Cohesion |
| One concept under two names; a "this" that could mean two things; stacked "Moreover" | Cohesion |
| An action hidden in a noun ("perform the computation of") | Clarity |
| A teaching move the content does not need (a forced bridge, a worked example of a definition, an essential condition hidden in an insight) | Cognitive load |
| Study pitched above or below the teaching profile; Exam re-teaching what Study teaches | Cognitive load |
| A running example whose givens change without notice | Correctness |
| Unrelated new ideas combined before the learner has what they need to follow them | Cognitive load |
| A prerequisite the student must recall from far back, with no reminder or link where it is used | Cognitive load |
| Text that spells out a matrix, vector, table or graph instead of showing it | Representation |
| A full re-explanation of an idea taught elsewhere | Redundancy |
| A worked calculation whose reusable rule is never stated | Intuition |
| Lines about the material ("the lecture groups…") | Clarity |
| An outcome taught but never practised | Coverage |
| A critical lecture example missing, or replaced by an invented case | Coverage |
| A lecture example with changed inputs, skipped states or another picture (a tree drawn as a table) | Correctness |
| A graph given as an edge table, a board or grid given as a table of coordinates, a walkthrough whose results show before its steps, or a whole slide pasted where a crop and the lesson's own words belong | Representation |
| The same mechanism worked twice, or a worked run replayed as a practice answer | Redundancy |
| A formula lookup written as a decision step, or two first moves in one pattern | Organization |
| Two cases of a decision step that overlap | Correctness |
| A past instance or example that no case fits | Coverage |
| Which-case feedback that only says right or wrong | Practice |
| A pitfall that describes the mistake instead of showing it | Representation |
| A pitfall without the task moment it happens in | Representation |
| A cheatsheet method without its steps, or a formula without its meanings | Clarity (cheatsheet) |
| Exam-relevant source material, of any kind, with no cheatsheet entry | Coverage (cheatsheet) |
| A pitfall without the rule its wrong line breaks | Intuition |
| A displayed formula whose variable the reader must recall from elsewhere, with no meaning on it | Clarity |
| Every index and constant of a formula marked with a meaning | Cognitive load |
| A variable meaning repeated in the sentence beside its formula | Redundancy |

## Correctness

Facts, notation, numbers and conventions match the cited source and edition.

- `correctness.source_match`: every definition, claim and value agrees with the cited page.
- `correctness.recomputed`: every number is recomputed with code: examples, trace states,
  table cells, plot points, answers, hints and the numbers inside feedback.
- `correctness.answer_key`: every answer, explanation and option feedback agrees with
  your own solution.
- `correctness.conventions`: the conventions an answer depends on (tie-breaks, order,
  indexing, rounding) are stated before the task, or every valid alternative is accepted;
  a running example keeps its givens unless the text says they change.
- `correctness.citations`: each citation opens the page that says it.
- `correctness.cases_exclusive` (Exam pattern): a decision step's cases never overlap, and
  every listed past instance, example and part falls under exactly one of them.

2: correct, but a convention is left implicit or a citation points at the wrong page.
1: a wrong fact, number, answer or trace step.

## Clarity

The student can read each passage once and know what it says.

- `clarity.one_reading`: short, direct sentences; one idea per paragraph.
- `clarity.terms_defined`: each term is defined where it is introduced and marked
  `{{term}}` later.
- `clarity.notation_unpacked`: a notation-heavy statement says its claim in words, reminds
  the reader in one line what each symbol means here, works a concrete case, and only then
  states the general identity with its symbols and conditions.
- `clarity.symbols_recall`: in displayed formulas, the variables a reader would stop to
  recall (defined elsewhere, compound or easily confused, shifting meaning, a formula used as
  a tool) open a meaning that says what each is here, in about twelve words; obvious indices,
  constants and just-defined variables are not marked; no meaning only renames its variable.
  Strict for Exam pattern applied formulas and cheatsheet formulas, judged for Study and
  Exercises ([variable meanings](../../prepare-study/references/variables.md)).
- `clarity.clear_task`: every prompt says what the student produces.
- `clarity.case_observable` (Exam pattern): a case's `when` names something the student
  can see in their working at that step, and its `then` names one move.
- `clarity.no_meta`: no line about the material itself ("the lecture groups…",
  "Authored example:") or that tells the student to work
  ([writing](../../prepare-study/references/writing.md)).

2: a dense paragraph, an undefined term or an ambiguous instruction.
1: the main idea cannot be understood from the text and its pictures.

## Cohesion

The student never has to reach the end of a sentence, paragraph or section to make sense of
its start ([writing](../../prepare-study/references/writing.md)).

- `cohesion.familiar_first`: sentences start from what the reader has (the topic, the
  result just reached, the term the last sentence ended on) and end on what is new.
- `cohesion.point_first`: each paragraph and block opens with its point; the opening
  sentences of a section alone tell its argument.
- `cohesion.linked`: a first-time reader can tell how each section and block relates to
  the one before (follows from it, contrasts with it, specializes it, a parallel case), and
  the text states the relation where they could not infer it.
- `cohesion.honest_connectives`: a connective marks a real turn ("so", "but", "because");
  none is stacked for flow.
- `cohesion.one_term`: one term per concept and one notation per quantity across the item;
  every "this" and "it" has one possible referent.

All checks for Study units and Exercise guides and solutions, which first-time readers meet;
Exam keeps `cohesion.one_term` and no unexplained jump, because its reader has studied the
ideas and linking sentences there are redundancy.

2: one abrupt jump, a term switch, or a paragraph whose point comes last.
1: the reader cannot follow how the ideas connect without rereading.

## Cognitive load

What the student has to hold in mind at once.

- `cognitive_load.one_new_idea`: each section or step has one coherent teaching purpose.
  New terms, symbols and cases come in an order the learner can follow without guessing
  missing steps.
- `cognitive_load.first_encounter`: walked in reading order by someone who knows only
  what earlier sections and units taught, no section asks them to hold new symbols or
  terms they cannot yet picture, and no line asks them to guess a missing step.
- `cognitive_load.reminder_at_use`: a prerequisite taught far back (another unit, or many
  sections earlier) gets a one-line reminder or a `{{term}}` link where it is used, so the
  student need not navigate away. This is reinforcement, not redundancy.
- `cognitive_load.short_prose`: no paragraph longer than two sentences or 45 words; a
  procedure comes as labelled steps and a worked example as one meaningful operation per step.
- `cognitive_load.math_set`: every symbol and formula is set as mathematics, not typed
  characters; a displayed or structural quotient is a fraction (`\frac`), not a slash or
  `\div` chain, and no inline fraction is so tall or nested that it breaks the line
  ([notation](../../prepare-study/references/content.md#notation)). Units, `d/dx`, code
  and short incidental `n/2` are fine.
- `cognitive_load.together`: text and the picture it refers to sit together.
- `cognitive_load.fits_student`: Study can be followed by a first-time reader who knows
  the teaching profile's prerequisites, without over-explaining what they already know;
  Exam stays concise and reaches depth through Recall instead of re-teaching.
- `cognitive_load.moves_fit`: every teaching move earns its place for this content; a
  worked example of a one-line definition, a bridge between parallel cases, an analogy that
  adds nothing or an essential idea hidden in an insight is a finding.

2: unrelated ideas introduced before their prerequisites, a long question, or a trace followed
without its state.
1: the student must combine several unexplained pieces before anything makes sense.

## Representation

Each idea is shown in the shape it has ([representations](../../prepare-study/references/representations.md#choose-the-representation)).

- `representation.shape_fits`: procedures are traces with their state, parallel cases
  tables or lists, two-input rules matrices, physical or spatial ideas drawn figures,
  symbols formulas with each symbol explained, structures diagrams or trees.
- `representation.shown_not_described`: a matrix, vector, table, graph or state that the
  text names is shown itself ("\(P = \begin{pmatrix}1&0\\0&0\end{pmatrix}\)"), and the
  text says what to notice in it; prose never asks the student to picture an object from
  a description of its entries ("the diagonal matrix with entries 1, 0").
- `representation.process_shown`: apply the packet rule to the complete process and
  its intermediate states.
- `representation.picture_carries_data`: a question's picture carries the data the
  question needs.
- `representation.prose_points`: the text beside a picture tells the student what to look
  at in it, in reading order.

2: an idea that has a shape is given as prose, a picture needs prose to be read, or a
visual scores 2.
1: the central idea of the item has no fitting picture, table, formula or code, or a
visual scores 1.

Representation never scores higher than the item's weakest visual; the scorecard rejects it.

## Practice

Cards, questions and exercise steps make the student use the outcomes.

- `practice.new_case`: authored application questions require an unworked input or
  decision. Replaying an unchanged worked input and answer is recall. Routine application
  with new values is useful; require substantive transfer when the objective calls for
  it. A taught general rule does not solve every later instance. Compare the actual
  inputs and requested result; shared numbers or graph structure alone are insufficient
  evidence of replay. Retrieval cards and released statements are exempt.
- `practice.plausible_options`: options are plausible, and each wrong option's feedback
  names its mistake.
- `practice.hint_ladder`: hints go from a pointer to the first operation to Compare and
  never give the answer. A large guided step has a middle hint.
- `practice.complete_answer`: Compare and the solution answer everything that was asked.
- `practice.case_feedback` (Exam pattern): which-case feedback names what in this question
  decides each case, never only right or wrong.
- `practice.interleaved` (Exam pattern): Practise items change the setting of the worked
  examples, and neighbouring items need different cases.

2: a question re-asks a worked case or is answered by its own stem, a distractor is
implausible, or a hint gives the answer.
1: practice tests something the item does not teach, or an answer is missing.

Whether every outcome is practised at all is scored under Coverage.

## Coverage

The item teaches what its sources say students should learn.

- `coverage.ledger_outcomes`: every outcome the coverage ledger assigns to the unit is
  taught and practised.
- `coverage.all_parts`: an exercise answers every part of the original.
- `coverage.cases_complete` (Exam pattern): every listed past instance and example needs
  only the listed cases; a case the exams never need is a `cognitive_load.moves_fit` finding.

2: an outcome is taught but not practised.
1: an assigned outcome or an original part is missing.

## Intuition

The student leaves knowing why the idea works and when to use it, not only its steps.

- `intuition.motivated`: a first-time reader can tell why each new idea comes where it
  does: the problem it solves, the limit of the previous idea, a concrete case, or its use
  just after. The means fits the idea; a forced motivation is a `cognitive_load.moves_fit`
  finding.
- `intuition.concrete_first`: where the idea is abstract or notation-heavy, a worked example
  or picture comes before the general rule.
- `intuition.reasons`: every step connects its own facts to the rule that permits it.
  Calculations show the inputs, substitutions and arithmetic; qualitative decisions
  show their premises and inference. Repeated wording is a signal to inspect, not proof
  of missing reasoning when the step's evidence is already visible.
- `intuition.misconception`: where students hold a known wrong belief, it is named and shown
  to fail.
- `intuition.prediction`: where the item asks for one, the student predicts before a result
  is revealed: in an exercise step or a practice question; a lesson does not ask for
  predictions.
- `intuition.limits`: the item says where the idea stops working.
- `intuition.general_rule`: a worked calculation that instantiates a reusable rule
  states that rule with its symbols, conditions and use. Add another application only
  when it tests a new condition, decision or misconception. Do not add another calculation
  of an already-known operation or formulas to descriptive material. A rule left to be
  inferred from one example is a finding.

2: correct and complete, but a rule arrives without its reason, the example comes only
after the abstract definition, or a known misconception goes unaddressed.
1: the student can repeat the steps but not say why they work or when they apply, or an
analogy misleads.

## Organization

The page reads in the order its ideas depend on each other, and its outline helps.

- `organization.dependency_order`: each section uses only what earlier sections or
  earlier units taught; no `{{term}}` before the section that defines it.
- `organization.outline`: titled sections form a Contents list a student can scan:
  heading levels nest, titles are short, distinct and parallel, and each says what the
  section teaches. Examples and supporting arguments nest under their topic instead of
  appearing as unrelated peers; genuinely parallel topics stay at the same level.
- `organization.builds_up`: each section comes once what it builds on is in place;
  nothing is said out of place (a pitfall before its method, a recap in the middle). How a
  section relates to the one before is `cohesion.linked`.
- `organization.plan_followed`: where the unit has a teaching plan, the item does what the
  plan decided, or the plan records why it changed.
- `organization.parts_in_order`: an exercise presents its parts in the original order,
  each followed by its own guide after all its supporting blocks, and each step builds
  on the previous one.
- `organization.fork_placement` (Exam pattern): a fork that only picks a final formula is a
  cheatsheet entry reached through Recall, a fork that changes the next move is a decision
  step, and different first moves are separate patterns.
- `organization.example_shape` (Exam pattern): cases that past papers ask together are
  parts of one example; a case that needs its own setting has its own example.

2: one section out of order, a vague or repeated title, or a skipped level.
1: the page cannot be followed in reading order: results are used before they are
derived, more than once.

## Redundancy

Every idea has one full explanation on the page, in the form that teaches it best.
Repetition is judged by its effect on the student, not counted.

- `redundancy.said_once`: no fact, rule or example is explained in full twice, and no
  passage repeats another in the same words. A variable meaning shown on demand is the one
  explanation for its context; repeating it in the text beside the formula is the repeat.
- `redundancy.text_restates_picture`: text and captions add to their picture, table or
  formula instead of repeating it.
- `redundancy.prompt_restates_picture`: a question's prompt and its picture do not repeat
  each other.
- `redundancy.distinct_practice`: no two cards or questions ask the same decision in the
  same form.
- `redundancy.no_repeated_labels`: no repeated citation, label, assumption or
  instruction.

Not redundancy (purposeful reinforcement): the closing recap of two to four points; a
one-line prerequisite reminder or `{{term}}` where an earlier idea is used; a recap in
different words before a hard step; a second example or non-example that shows the idea
from another side; a given restated inside the exercise step that uses it; a card that
retrieves what the lesson taught; a later question that asks for the same idea in a new
situation. Each must be short and point to the idea's home. Score the duplication, not the
reinforcement: a reminder that grows into a second lesson, or two adjacent passages that
say the same thing in the same form, is a finding.

2: one restated passage or caption, or two near-duplicate questions.
1: repetition doubles the length of a section or hides the new idea.

## Course organization

Units, groups and workspaces follow one order in which each idea builds on earlier ones.

- `organization.unit_order`: no unit uses a term, result or method that a later unit
  teaches; the map's `builds_on` points only backwards.
- `organization.links_back`: a unit that uses an earlier unit's idea links it, by
  `{{term}}` or by naming the unit, so the student can return to it.
- `organization.map_first`: the introduction or course entry point says what the prepared
  material covers and where to start. Do not require the first lesson to repeat a map
  already visible at entry.
- `organization.categories`: groups follow the course's `organization` (lectures, weeks
  or topics); a topic group holds several units, while a lecture or week group holds what
  that lecture or week taught; labels are short, parallel and distinct; there is no
  catch-all group and no folder around the whole course; a second level only for a large
  group.
- `organization.unit_size`: each unit teaches one coherent topic; units are of
  comparable size.
- `organization.one_backbone`: exercise sets and Exam topics follow the order of the
  units they need, or differ for a reason the course gives.

2: one forward dependency, one odd group (a lone unit, a catch-all, a unit in the wrong
group), or one unit that should be split or merged.
1: a dependency cycle or several forward dependencies, or groups that do not help a
student find a topic.

## Course redundancy

Each idea has one home where it is taught; everywhere else links to it or practises it
in a new form.

- `redundancy.one_home`: no idea is explained in full in two units. A short reminder
  that links to the home is reinforcement, not a second home.
- `redundancy.exercises_link`: exercises link the Study passage they need instead of
  teaching it again.
- `redundancy.exam_compresses`: cheatsheet lines compress Study. Expanded details give the
  compact conditions, meanings, steps or reference objects needed for revision and link
  the full lesson. Do not copy a full Study explanation.
- `redundancy.distinct_pool`: Revision pools all units, so no two units hold
  near-duplicate cards or questions.

Not redundancy: spaced or interleaved practice of an outcome, a faded or transfer
version of a worked example, or a later unit that revisits an idea to take it further.

2: one idea explained in full in two places, or one duplicated question pair.
1: a workspace largely repeats another: copied passages, or the same worked example in
the same form.

## Integration

Scored only when the report's `course.dimensions` lists it: when two or more workspaces
(Study, Exercises, Exam, Lecture) are prepared, or media links to a prepared workspace.
They aim at the same outcomes
and send the student to each other.

- `integration.prerequisite_links`: each exercise links the prepared unit and passage
  that teaches its prerequisite when one exists. Otherwise retain its explanation and
  recorded prerequisite gap.
- `integration.exam_links`: Exam concepts link the prepared Study passages that teach
  them, when those passages exist. Otherwise record why no link fits; do not add
  unrequested Study content.
- `integration.entries_apply`: cheatsheet entries link matching prepared Study passages
  and the patterns that use them. Record a reason when no link fits. A pattern's workflow
  appears only in the entry that names it as its method.
- `integration.lecture_links`: units link the Lecture of the lectures they teach.
- `integration.same_notation`: terms, symbols and conventions are the same in every
  workspace, and marked terms open the Study definition.
- `integration.difficulty_climbs`: the prepared sequence supports transfer without copying
  authored questions unchanged. Preserve the level and wording of released exercises.
  Individual items need not increase in difficulty. Do not weaken Study practice or add
  unrequested material to force a difficulty ladder.
- `integration.media_links`: media follows its exact Study/Exercise target and
  actual prerequisites, with consistent notation and disclosed modality limits.
  Alternative access is not a second competing home for the idea.

2: a link to a weaker block, one notation or convention that differs, or a workspace
that repeats another's question without extending it.
1: an exercise needs knowledge no linked passage teaches, two workspaces contradict each
other (another convention or answer), or a workspace links to nothing.

## Cheatsheet

The cheatsheet (`exam/sheet`) is one item, read in one `cheatsheet` pass against the
course sources and the exam requirements in the coverage ledger. It is a revision
reference, not a lesson: it needs no practice, intuition or teaching moves, and a
one-line fact that is complete as written needs no expansion.

- `correctness.sheet_true`: every statement, list member, table cell, condition, unit,
  threshold and code behaviour matches the cited source for this course and its exam
  period; a rule keeps its direction and its exceptions.
- `coverage.sheet_inventory`: every exam requirement the sources state is held by an
  entry or recorded as a gap with a reason, including facts, definitions, rules, lists,
  classifications, comparisons, code and frameworks, not only formulas and methods; a
  source read for the sheet but without requirements is a finding.
- `clarity.sheet_sufficient`: each entry can be used as read: its line states the claim
  with the condition that makes it true; a formula opens its variables' meanings; a method
  opens its steps (details or `workflow_from`); a list or comparison is complete.
- `clarity.sheet_concise`: text reads as Study text does: one claim per sentence, at most
  two sentences or 45 words a paragraph, conditions and caveats as points, maths set as
  maths, no aside that changes nothing the student does.
- `clarity.sheet_meanings`: every variable in an entry's maths opens its meaning (the
  formula's `symbols`, or the entry's own `symbols` for maths in its line, tables or text);
  no meaning list typed as a sentence ("\(b\): maximum branching, \(d\): ...").
- `representation.sheet_form`: each entry takes the form its retrieval task needs: a
  table for a comparison or a two-input rule (both axes labelled), a list for members or
  obligations, a tree for a classification, code for syntax or structure, a figure for a
  shape or state, a formula with meanings; never a paragraph that spells one of these out.
  Fractions follow the notation policy: a displayed quotient is a fraction, compact
  inline forms only where they read better.
- `organization.sheet_grouping`: topics and their sections (`path`) put related
  references together in course order, so a student finds and compares them; no global
  buckets by form ("Formulas", "Facts").
- `redundancy.sheet_expansion`: an expanded entry adds substance (conditions, meanings,
  steps, the table or code itself); it does not repeat its line, another entry or the
  Study lesson, and no entry is padded to justify expanding.

2: one missing requirement, one wrong condition or cell, one entry in a form that hides
its structure, or one padded expansion.
1: a wrong rule or value a student would use in the exam, several missing requirements,
or a sheet reduced to formulas and methods while the sources rest on other knowledge.
