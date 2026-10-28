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
new question; create a new one only when the first steps differ.

- **Cues**: what a student can see in the question text (a structure, a given, a
  phrasing). Never the concept's name, because the exam does not print it.
- **Workflow**: the steps an expert takes, each one action, with an optional reason.
  It must solve every listed instance; check it against each one.
- **Template**: the answer skeleton - a proof frame, a table to fill, a code shape,
  the structure of a good explanation for theory questions.
- **Marking points**: what earns points. `official` only from a marking scheme or
  official solution; otherwise `inferred`. Never grade prose by keywords.
- **Pitfalls**: where students actually lose points; **variations**: how the pattern
  changed across sittings (a new constraint, another representation, a reversed
  question).
- **Worked practice** (required): one question, a past one with its stored statement
  and solution or an authored one, solved through the workflow. Its `steps` apply
  every workflow step in order (several steps may apply one workflow step). Each
  step asks for exactly that move, may give a hint, takes an answer in a short form when one
  fits (a choice is checked; any other answer is compared), and always shows the worked answer, filling in the
  template where there is one. For code patterns, the steps that matter write code from a
  starter signature and compare with a model answer. Solve it yourself; label an official solution only
  when it is one.
- **Drill**: up to a few checked items that practise the decision the workflow makes.

Every question you write here, worked practice and drills included, shows its
situation with code, a diagram, a UML diagram, a formula, a table or a plot beside the text; the
build rejects text-only ones. A worked practice on a text-only past question adds the
picture in a worked step. Choose the representation as in prepare-exercises'
[content](../../prepare-exercises/references/content.md#show-the-question-not-only-tell-it).

The order of patterns comes from `exam-report --section stats`: sitting occurrence,
points share when every mark is known, and recent appearance. It is a study guide,
not a forecast; with few exams the app says so.
