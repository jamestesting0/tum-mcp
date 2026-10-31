# Teaching quality gate

Use the course's objectives and prerequisite/notation map. Choose units by a
coherent dependency or learning goal; keep an established course sequence when useful.
Read relevant stored passages once and retain their locators for authoring/review.

For each affected goal, keep a short private authoring note: what the student must
do → prerequisite reasoning/notation → inference and its conditions → example or
counterexample → independent practice demand → source locator. Reuse existing
notes; this is a review aid, not a curriculum database or required student screen.
Explain why the next operation helps and what makes it valid. A procedure without
its reason leaves students unable to choose it in a new problem.

A prediction before an explanation invites an attempt; it is not a failing grade.
A teaching check asks for one newly explained inference on a fresh case. Later
practice asks students to select and use the idea without its method in the title.
Use these when they help; do not insert a question after every paragraph. Keep
independent reading possible without obligatory forms or prerequisite quizzes.

## Lesson shape

Each unit reads as one short lesson, built from ordinary blocks (the app does not
label these roles; the writing makes them clear):

1. Summary: the problem the unit solves, in one or two sentences.
2. Objectives: observable outcomes such as trace, explain, choose or compute, taken from
   the source's own outcomes in the coverage ledger.
3. Orientation and bridge: the first section says what the new object describes, why
   it matters and which earlier idea it extends, with a one-line reminder of that idea.
   Name the parts the student will meet (the sphere's poles and equator, the angle, the
   phase) before any formula relies on them, one at a time. `study report` flags an
   opening that introduces several new symbols or terms before any picture or example as
   `dense_introduction`.
4. Intuition: a concrete case or picture before the formal statement.
5. Definitions: a `definition` block right after the passage that introduces each term
   students must learn. It appears inside that passage as the term above its meaning, so
   the prose does not restate it. Later mentions anywhere in the course are `{{term}}`.
6. Mechanism as labelled `steps`, one action each, then a worked example in its own
   section: one computed value per step, a `derivation`, or a trace. When a procedure
   has several dependent transformations or a changing state, a derivation with
   `walkthrough` lets the student step through it, with the state drawn beside each line.
7. General rule: after the worked case, the reusable rule as a formula block (every
   symbol defined, its conditions and domain, when to use it), then one application to
   different numbers. Comparing the two cases is what lets the student abstract the rule;
   a rule left to be inferred from one example is flagged as `example_without_rule`.
   Skip it when the topic has no reusable rule; never list identities detached from use.
8. Pitfall: the common misconception or limiting condition, where it applies.
9. Recap: for units with more than three sections, a final text block with two to
   four points a student should recall without the page.

Flashcards test recall of those points; practice tests application. Review mode
reuses Again ratings and wrong answers, so every objective needs at least one card
or question that a student can genuinely get wrong.

For each new or changed objective, cover the mechanism, its assumptions and a useful
example, each in the shape it has ([representations](review.md#choose-the-representation)):

- One idea per passage, with at most 70 words of prose, structured as in
  [writing](writing.md#structure-before-prose). A passage is not automatically a
  top-level section: group a method's cases, examples and limitations beneath that
  method using the [heading hierarchy](content.md#blocks).
- A procedure or hard argument: labelled steps. An algorithm's run: a trace whose frames
  carry its state ([traces](review.md#algorithm-traces)).
- Parallel cases: points or a table. A rule with two inputs: a decision matrix.
- Anything with a physical or spatial shape: a drawn figure.
- Prose says only what the picture cannot (why it works, when it fails) and names what to
  look at, in reading order.
- Essential conditions and counterexamples stay visible; optional proof detail may sit in
  a disclosure, essential meaning never.

Split independent goals and remove duplication. Teach each idea in full in one unit, its
home; later units mark it `{{term}}` or build on it. Reinforce on purpose where a
first-time reader needs it: a one-line reminder of a prerequisite where it is used, a
recap in different words before a hard step, a second example or non-example, a revisit
after a gap that takes the idea further. Keep each reminder short and pointing home; a
reminder that grows into a second lesson is duplication. Order units so each uses only
what earlier units teach. There are no diagram quotas and no equal word, card or
question counts.

## Notation at the point of use

A notation-heavy statement is read by someone who may not yet hold every symbol. Where
it appears:

1. Say the claim in words first, on a concrete case: "\(\lvert 0\rangle \otimes
   \lvert + \rangle\) and \(\lvert 1\rangle \otimes \lvert + \rangle\) are orthogonal".
2. Give a one-line local reminder of each symbol the claim needs, in this context: a ket
   is a state vector, \(\langle a \mid c\rangle\) its inner product with another, \(\otimes\)
   combines two systems, orthogonal means inner product zero. Mark the term `{{term}}`
   for the full definition; do not send the reader away for every symbol.
3. Work the case: first factors \(\langle 0 \mid 1\rangle = 0\), second factors
   \(\langle + \mid + \rangle = 1\), product \(0\). Use a `derivation` when there are
   several lines.
4. Then the general identity as a formula block with every symbol and its conditions,
   linked to the case ("the case above is \(a = 0, b = +, \dots\)"). State the condition
   that changes a computation, such as conjugate-linearity in the first argument and
   linearity in the second when extending to sums.

`study report` flags an identity over four or more symbols inside a sentence as
`unexplained_identity`. This applies to any notation: probability, logic, complexity,
physics, not only quantum mechanics.

## Precision and language

Define each term before a table, step or question uses it: a comparison table whose
columns name properties the student has not met yet teaches nothing. Define symbols
and units, verify signs/indexing/edge cases, and check equations
against the original when OCR is uncertain. Keep prose, formulas, tables, cards
and feedback consistent about the same assumption. Keep instructor facts apart from
derived explanation, but do not label examples or narrate the source.

Every sentence must teach. Cut lines that only restate a title, describe the page or
tell the student to read, work or compare; the app already shows how to use itself.
Follow [writing](writing.md): short active sentences, one idea at a time, consistent
technical terms and the lecturer's notation, and no sentences about the material itself. Aim around 20–25 words; do not spend iterations counting words
or sacrifice qualifications to meet a limit. Respect the user's language. These
local rules adapt [STE structural guidance](https://github.com/danyuchn/asd-ste100-skill/tree/c7b11cd9258708909d8574c8176d4c70969c8b29);
that link is provenance, not required research. No certified dictionary claim.

## Retrieval and assessment

Cards test one recall item or discriminating comparison before reveal; avoid
essay backs and clues. A multiple-choice question has one defensible answer under
stated assumptions and plausible distractors based on realistic misconceptions,
four options by default. Give specific feedback for every option; revise the
question if a useful distractor is missing instead of adding filler. Feedback
explains; it does not restate the verdict, which the app already shows.
Prefer application/transfer where the
objective requires it; avoid tricks, double negatives, all/none shortcuts and
length clues (the app shuffles positions). Check EVERY new/changed option independently. If two
answers are defensible, repair the question/assumptions rather than forcing a key.

Audit objective → explanation → card/question → source. Work the example, trace or
counterexample independently of the written answer. A schema pass cannot verify
subject matter. Use an open/worked task when coding or proof construction matters;
MCQ results and self-ratings do not establish mastery or official exam coverage.
Recheck only affected teaching and dependent claims after a change, not the whole bank.

Use [practice.md](practice.md) for question families, portable givens and repair feedback.

## Supporting context

Apply [Explore](explore.md) at source triage and review with Explore closed. Keep the
motivation, definitions and examples needed for understanding in Content; retain
independent context separately when the evidence supports that choice. Do not create
cards or questions solely to test optional trivia.
