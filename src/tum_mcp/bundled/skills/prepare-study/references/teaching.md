# Teaching quality gate

Use the course's teaching profile, objectives and prerequisite/notation map. Choose units
by a coherent dependency or learning goal; keep an established course sequence when useful.
Read relevant stored passages once and retain their locators for authoring/review. Decide
how each idea is taught in the unit's [teaching plan](planning.md) before writing blocks.
Explain why the next operation helps and what makes it valid. A procedure without
its reason leaves students unable to choose it in a new problem.

Study explains; it does not ask for predictions (those belong in Exercises).
A teaching check asks for one newly explained inference on a fresh case. Later
practice asks students to select and use the idea without its method in the title.
Use these when they help; do not insert a question after every paragraph. Keep
independent reading possible without obligatory forms or prerequisite quizzes.

## Teaching moves

Study is read by a student who meets the topic for the first time and knows the profile's
prerequisites. After a unit they can say why each idea exists, use it on a new case and say
when it fails. How to get there depends on the idea: choose moves by what makes it hard, and
add none the content does not need. A forced move (a worked example of a one-line
definition, a bridge between parallel cases, an analogy that adds nothing) costs attention
like any filler.

| Move | Use when | Skip when |
| --- | --- | --- |
| Start from a problem or limitation | The idea removes a limitation of an earlier method or answers a real question | A building block that its first use, just after, motivates; one of several parallel cases |
| One-line reminder of a prerequisite | Taught in an earlier course (profile) or a distant unit | Taught in the previous section |
| Concrete case before the rule | The idea is abstract or notation-heavy | A simple fact, or the case would be artificial |
| Name the parts first | The mechanism has several new parts to track (poles, angle, phase) | One new term |
| Labelled steps, then a worked example | A procedure or calculation with interacting steps: one computed value per step, a `derivation`, or a trace; a `walkthrough` when the state changes line by line | Definitions and single facts: practise them instead |
| Running example | Several concepts act on one setting; keep its givens unchanged | Independent concepts, or a contrast needs another case |
| Contrast, non-example or misconception | The idea is easily confused with a neighbour, or students hold a known wrong belief; a wrong move made at one moment is a `pitfall` callout (at most one per section) | Nothing nearby to confuse |
| General rule after the case | A reusable rule exists: a formula block with every symbol, its conditions and when to use it; another application only if it tests a new condition or misconception | Descriptive or one-off content; extra arithmetic that tests only an already-known operation |
| Relation sentence | The next idea follows from, or contrasts with, this one and a first-time reader could not infer it | Parallel cases: a table or one framing line |
| Recap of two to four points | Several ideas to retrieve | A short single-idea unit |
| Insight (a titled block's `insight`, behind a light bulb) | Optional depth: an application, a deeper why, a link to later topics | Anything needed to follow the page or do the practice |

Starting points by subject, which the profile and plan may override: mathematics shows the
concrete object first, derives with reasons and contrasts cases; algorithms run one instance
with its state and introduce each method by the limit of the previous one; programming and
design go from problem and forces to design and consequences, code before abstraction;
conceptual topics use cases, non-examples and decision matrices.

Whatever the moves, every unit has:

- A summary: the question it answers, in one or two sentences, never a copy of an objective.
- Observable objectives (trace, explain, choose, compute) taken from the source's own
  outcomes in the coverage ledger, or from an idea the source develops at length. An aside
  of the slides is not an objective, and every objective has a card or question.
- A `definition` block right after the passage that introduces each term students must
  learn. It shows inside that passage as the term above its meaning, so the prose does not
  restate it; later mentions anywhere in the course are `{{term}}`. State the course's
  fullest form: when a later lecture's digest defines the term with conditions (a rational
  agent maximises expected performance given its percepts and knowledge), give that form or
  say where the course makes it precise; `definition_refined` flags a shorter one.

## Give a concept its meaning, then show what it decides

Identify the new course concepts and properties a student must distinguish or use,
including terms in headings, comparison tables, guarantees and questions. Give each
its concise, source-faithful general meaning in a `definition` block at its first
teaching use, or link its verified earlier definition. Formal English is sufficient;
preserve the defining conditions and words such as every, some, if and only if.
A heading, one successful example or the conditions for one algorithm's guarantee
does not state the property's meaning.

For example, completeness means a solution is guaranteed to be found whenever one
exists in the stated problem class. Finite branching and shallowest-goal depth are
conditions under which BFS has that property; the finite-layer argument explains why.
Keep those distinct. A complete search need not return the cheapest path or enumerate
every solution. Use the course's actual conventions when teaching these claims.

Connect the definition to a concrete case and, where confusion is likely, a nearby
nonexample or changed condition that exposes its boundary. Reuse a suitable worked
case instead of adding another merely to fill a template. A fresh application or
explanation checks the distinction; a recall card alone checks only its wording.
An unfamiliar incidental word needs a short gloss, not a new assessed concept. For
an abstract idea, a motivating case may come first, but its general meaning must be
clear before a student is asked to use it.

These choices follow [IES guidance on abstract/concrete connections and explanatory
questions](https://ies.ed.gov/ncee/wwc/PracticeGuide/1) and
[concept analysis with discriminating examples](https://pmc.ncbi.nlm.nih.gov/articles/PMC8458507/).
They are teaching tools, not a fixed number of definition cards or examples.

`study report` flags `dense_introduction` (several new symbols or terms before any picture or
example) and `example_without_rule` (numbers worked without a general rule); read them in
place, since some topics have no reusable rule.

Flashcards test recall of those points; practice tests application. Review mode
reuses Again ratings and wrong answers, so every objective needs at least one card
or question that a student can genuinely get wrong.

For each new or changed objective, cover the mechanism, its assumptions and a useful
example, each in the shape it has ([representations](representations.md#choose-the-representation)):

- One idea per passage, structured as in [writing](writing.md#structure-before-prose);
  split a passage that holds two ideas. A passage is not automatically a
  top-level section: group a method's cases, examples and limitations beneath that
  method using the [heading hierarchy](content.md#blocks).
- A procedure: complete labelled steps, pseudocode or a flowchart with explicit control
  flow ([procedures](writing.md#structure-before-prose)). A hard argument: labelled steps.
  An algorithm's run: a trace whose frames
  carry its state ([traces](representations.md#algorithm-traces)).
- A test, procedure or argument the unit teaches is shown at work once, not only named: a
  test as one run with its verdict (an exchange as a table of questions and answers, not
  narrated), a logical argument as its premises above its conclusion, each on its own line
  (a `formula`, `derivation` or list; `inline_steps` flags them run together), an agent as
  one decision scored by its measure. Each plan
  concept names that instance and the block that shows it; checkers ask concept by concept.
- The members of a list (four capabilities, three methods) as a list or table, never a
  sentence; `inline_list` flags them.
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
