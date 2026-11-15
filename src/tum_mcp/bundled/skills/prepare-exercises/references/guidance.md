# Help with the next inference

Use the course's teaching profile, the moves in
[Study teaching](../../prepare-study/references/teaching.md#teaching-moves) and the distinct
demands in [practice](../../prepare-study/references/practice.md). A step may assume the
profile's prerequisites and what earlier units teach; it reminds the rest in one line.

Keep the original problem first and useful on its own. Plan the steps from your own
solution, not from the statement:
1. Solve the part and list its subgoals: the intermediate results or decisions the
   method passes through, such as "find the evidence \(P(+)\)" or "prune the
   neighbours of A".
2. Make one step per subgoal a student could get stuck on. Name the subgoal in the
   prompt. A part usually needs two to five steps; a one-line part needs one.
3. Keep routine operations, such as an addition or a substitution, inside the step's
   working. A step never asks for one arithmetic operation.
4. Ask for the next piece of work. Do not add "explain why" questions; Compare
   explains.

Each step's purpose names the reasoning difficulty it addresses: choosing a premise,
interpreting a symbol, constructing an invariant or combining two results. Omit
ceremonial instructions such as "read the problem". The app shows one step at a time
with the statement still reachable, and the Solution is always available without
passing steps.

Review the reading order with every guide closed: shared context, part (a) with its
supporting material, its Guide and Solution, then part (b) with its own controls. Use the explicit
[`part_blocks` anchors](content.md) rather than adding numbered labels to a stack of
guides at the bottom. Opening a guide must not separate the next question from its
own figure or table. Inside it, step headings and rich blocks nest beneath that part.
Open a Solution before touching its guide: it must reveal just that question's answer.
Opening or closing one solution must leave the others and guide progress unchanged.

Walk the exercise once as a student meeting it for the first time: which earlier
definition each step needs, which new symbol appears, and where a step jumps. Put a
one-line reminder of that definition in the step that needs it (with its `{{term}}` or
prerequisite link); this is reinforcement, not redundancy. Sequence the steps so
responsibility passes to the student: later steps get shorter prompts and fewer
hints. The Compare working stays complete in every step. Keep every reminder and hint optional and never reveal the answer by
default.

An early hint points to a relevant relation or asks a smaller question. A later
hint works the first operation; Compare completes it ([hint ladder](../../prepare-study/references/representations.md#help-before-the-answer)).
A step whose answer has many parts gets that middle hint or is split. Add only useful
hint levels, without quotas. A check's feedback repairs the earliest likely
error; the app shows it beside the expected answer when the student compares. An optional prerequisite link
and inline reminder can repair a gap without a separate prerequisite wizard.

Students work on paper and compare. Give a short answer where one exists: a number
with its unit, a filled table, a node/edge/path selection, plotted sample points, or
four options when choosing is the learning goal. When the answer is a calculation, the
Compare answer is a `derivation`: each meaningful transformation on its own line with a
short reason, so the student can find where their working diverged, and one labelled
group per requested quantity. Check the labels against the task (seven results asked,
seven shown). Several results in one sentence are flagged as `compressed_working`. A
derivation in a step or the Solution may give `symbols` for the variables a student would
stop to recall ([variable meanings](../../prepare-study/references/variables.md)). Use a rubric and model derivation for
proofs, code, design and other open work. For programming, a step asks the student to
write the method or class from a starter skeleton and compare with a model answer,
not to arrange or recognise given code. Every step does a real piece of the work; do
not add questions that only restate the statement. A rubric compares assumptions, essential reasoning
and conclusion, and admits equivalent approaches. Never use keyword matching or
pretend prose is automatically graded. Do not require typing, confidence forms, timers
or self-ratings. Every step stands on what the student has seen; see
[content](content.md#give-the-student-everything-the-answer-uses).

A part that asks who is right, which case applies or whether a claim holds gets a
verdict: apply the source's own definition (cite it with `pages`), say which claim it
supports, and correct the claim it refutes. "Both are partly right" is an answer only
when the definition itself splits the case.

State the conventions the answer depends on in the statement or step prompt. Review by
attempting the task without looking at its solution, then pass the
[draft checks](../../prepare-study/references/loop.md). Then simulate one
plausible miss and request only the next hint. It should help the student do the
next inference. Check an altered case where a condition fails; merely renaming
the original task is not a transfer check. Assistance and retries are not mastery
estimates. Finishing an exercise only marks it completed in the outline.

Prerequisites must resolve to core Study blocks. If solving a released task needs
something currently in Explore, record the dependency and repair core teaching when
Study is in scope; do not silently make optional reading mandatory. See
[Explore](../../prepare-study/references/explore.md).
