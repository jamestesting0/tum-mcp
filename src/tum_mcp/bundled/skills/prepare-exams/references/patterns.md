# Registry and patterns

## Extract every question

For each variant, list every subquestion with its number, points as printed (never
inferred), format and locator. Store the statement when it will be shown: worked
instances, guided past papers, the recognition drill and the near-copy check need it.
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
- **Example**: a past question with its stored statement and solution, or an
  authored one. Solve it yourself; label an official solution only when it is one.
- **Drill**: up to a few checked items that practise the decision the workflow makes.

The order of patterns comes from `exam-report --section stats`: sitting occurrence,
points share when every mark is known, and recent appearance. It is a study guide,
not a forecast; with few exams the app says so.
