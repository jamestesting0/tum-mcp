# Registry and patterns

## Extract every question

For each variant, list every subquestion with its number, points as printed (never
inferred), format and locator. Store the statement when it will be shown: worked
practices, guided past papers and the near-copy check need it.
Statement block titles stay neutral ("Question 3") so they never name the method.

Give each question a status:

| Status | When |
| --- | --- |
| `classified` | One to three patterns (the first is primary) and the concepts it tests. |
| `out_of_scope` | No longer taught or outside the course; give the reason. |
| `unreadable` | The scan or text cannot be read reliably; give the reason. |

Use `confidence: low` when the classification is a judgment call; `exam-report`
lists those for review. Nothing is dropped: the report shows every question's state.

## Define a pattern by its solving strategy

A pattern is a transferable way to solve a family of questions, not a topic name and
not one year's numbers. Reuse an existing pattern when the same workflow solves the
new question; create a new one only when the first steps differ. A pattern explains
choices and limits for a student who has studied the topic; it never re-teaches a
concept. The page shows a Recall row for its `concepts`, which opens the Study passage.

- **Cues**: what a student can see in the question text (a structure, a given, a
  phrasing). Never the concept's name, because the exam does not print it.
- **Workflow**: the steps an expert takes, each one action, with an optional reason.
  It must solve every listed instance; check it against each one. When the method only
  holds under conditions, the first step checks them; when the answer can be verified,
  the last step says how.
- **Decision steps**: only where this pattern's past questions, variations or forecasts
  really need different next moves; most patterns have none. Never invent a degenerate
  input (an empty sample, a single object, a zero count) to create a fork: an edge that
  matters is a pitfall or a line in the cheatsheet entry. The cases share the steps before
  and after the fork; a first step that only picks which method to use means one pattern
  per method, and a limit on how many patterns to write is met by covering fewer question
  families, never by merging methods into one. The step names the decision and
  lists two to six `cases`: `when` is something visible in the
  working ("substituting gives \(0/0\)"), `then` is the next move. Place each fork by
  what it decides:

  | The fork | Where it goes |
  | --- | --- |
  | Picks a final formula or value (the Master theorem's three results) | A cheatsheet entry, reached through Recall |
  | Changes the next move (\(0/0\) -> L'Hopital, \(c/0\) -> one-sided limits) | Cases on a decision step |
  | Changes the first moves | A separate pattern |

  Cases never overlap: every listed instance falls under exactly one.
- **Apply**: what a step or a case applies, which the student opens under it with a
  click. `do` or `then` names the move in one line; `apply` shows it: `text` (the rule in
  words, inline math allowed), `math` (up to four display formulas, written exactly as
  the answer uses them) and `code` with its `language` (the lines this step writes). Give
  it wherever a move uses a formula, a rule, an answer frame or code, so a line such as
  "form the weighted projectors" never stands alone; a step that only reads the question
  needs none. The answer's shape (a proof frame, a table to fill, a code skeleton) is
  split over the steps that write it; there is no separate template. An applied formula
  gives its variables' meanings in this pattern (`symbols`, required; a meaning written once
  serves every formula of the pattern), following
  [variable meanings](../../prepare-study/references/variables.md).
- **Marking points**: what earns points. `official` only from a marking scheme or
  official solution; otherwise `inferred`. Never grade prose by keywords.
- **Pitfalls**: where students actually lose points, each as `situation` (the moment in a
  task where it happens, as the student meets it: "Turning the amplitude after \(k\)
  iterations into a probability"), `wrong` (what a student writes there, the actual working
  or code, not a description of it), `right` (its correction) and `why` (the rule the wrong
  line breaks), one line each, with `step` when it belongs to one workflow step. Take them from marking schemes, solutions and exercise feedback.
- **Variations**: how the pattern changed across sittings (a new constraint, another
  representation, a reversed question).
- **Worked practice** (`examples`, required): questions solved through the workflow, past
  ones with their stored statement and solution or authored ones. When one calculates,
  its solution is a `derivation`, one transformation per line with the workflow step it
  applies as its reason.
  - How many: one example without a decision step. With one, the examples cover every
    case once, shaped like the course's exams: cases that past papers ask together become
    parts of one question (`part` on each step); a case that needs its own setting gets
    its own example. Each example adds a case the earlier ones left open.
  - Steps: each example, or each part, applies every workflow step in order (several
    steps may apply one workflow step). Each step asks for exactly that move, may give a
    hint and always shows the worked answer, written the way that step's `apply` shows.
    On a decision step the first step asks which case applies: give `case` and one
    `case_feedback` line per case naming the given that decides it ("the counts sum to
    12, so the maximum is inside the interval"); "not this case" teaches nothing. Ask about
    this question ("Substitute \(x=2\). Which case is this?"), not a bare "Which case
    applies?". The app shows the cases as the options. The student answers on paper; a choice is checked, anything
    else is compared. For code patterns, the steps that matter write code from a starter
    signature and compare with a model answer.
  - The question states its task in the first sentence, adds no filler such as "work
    through the steps", and shows everything the answers use: the current classes as UML
    or code, the data as a table, a programming task's files as a `files` block that
    steps point into with `code` references. A step that expects a new name gives it
    ("call it `Unit`"). Solve it yourself; record an official solution only when it is one.
- **Drill** (required): items solved without steps, each self-contained like the worked
  practice. Every case is practised again here in a new setting; name it in `cases`
  (never shown). Each item opens a Solution with its expected answer, the explanation and,
  for a full problem, a worked `solution`; only a multiple choice is checked on screen.
  A `self_check` already shows its full `model_answer` in that panel. Omit `solution`
  when it would repeat that answer; both fields are visible together.
  Try solving the drill without its key workflow step. Ask for the relevant working
  or change the givens if a student can get full credit while skipping that step.
  Order items so neighbours need different cases.

Every question you write here, worked practice and drills included, shows its
situation with code, a diagram, a UML diagram, a formula, a table or a plot beside the text; the
build rejects text-only ones. A worked practice on a text-only past question adds the
picture in a worked step. Choose the representation as in prepare-exercises'
[content](../../prepare-exercises/references/content.md#show-the-question-not-only-tell-it).

The order of patterns comes from `exam-report --section stats`: sitting occurrence,
points share when every mark is known, and recent appearance. It is a study guide,
not a forecast; with few exams the app says so.
