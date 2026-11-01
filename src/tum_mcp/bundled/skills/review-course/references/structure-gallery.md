# Structure calibration gallery

Before the first Structure or Course pass of a session, score three of these cases on
the [rubric](rubric.md) without reading their verdicts, then compare with
[Verdicts](#verdicts). On any disagreement, re-read the check the verdict names. Each
verdict follows a rubric check, which it names; none is a course owner's judgement yet.

## Cases

**forward-heuristic** (course). Units in order: 1 "Frame a search problem", 2 "Expand
the cheapest estimate" (A*), 3 "Estimate the remaining cost". Unit 2's trace says "A*
needs an {{admissible heuristic}}"; unit 3 defines *admissible heuristic*.

**misc-group** (course). Groups: "Lecture 1 · Agents" (3 units), "Lecture 2 · Search"
(4 units), "Misc" (2 units: "Big-O recap", "Python tips").

**short-lecture** (course). The course is organized by lectures. Lecture 5 (Games)
holds one unit; the lectures around it hold two or three.

**course-folder** (course). Every unit's `path` starts with "Fundamentals of AI"; the
lectures are its subgroups.

**retaught-in-exercise** (course, Study and Exercises). Exercise "Check a heuristic"
opens with three sentences that define admissibility again. Its prerequisite links unit
`heuristics` without a block.

**spaced-bfs** (course). Unit 2 asks which node BFS expands next from a frontier holding
B and C. Unit 6 (mazes) asks for the cell BFS reaches first in a new maze.

**table-retold** (item). A table lists four search strategies with their frontier, cost
and completeness. The paragraph under it says: "BFS uses a FIFO queue and is complete.
DFS uses a stack and is not complete. UCS uses a priority queue …" for all four rows.

**tie-break-clash** (course, Study and Exercises). Study breaks ties alphabetically. An
exercise's solution expands C before B on a tie, by insertion order, and does not say so.

**lecture-backbone** (course). Groups "Lecture 1" to "Lecture 4" with three units each;
every `builds_on` points to an earlier unit; exercise sheets 1 to 4 need the units of
lectures 1 to 4 in turn.

**pitfall-first** (item). Sections: "Overview", "Pitfall: overestimating", "More
details" (defines admissibility), "Notes".

**recap-points** (item). A six-section unit ends with "Recall": three points that
restate its key rules.

The cases below come from two subjects and calibrate reinforcement against duplication
and the first-encounter walk ([text](text.md), [structure](structure.md)).

**prereq-reminder** (item, quantum computing). Unit 6 "Unitary gates" checks that
\(H\) preserves length. Its section opens: "Recall the {{inner product}}
\(\langle a \mid b\rangle = \sum_i a_i^* b_i\) from unit 3." and then uses it.

**conjugate-retaught** (item, quantum computing). Unit 2 derives \(1/(a+bi)\) by the
conjugate in `block:2`. `block:7` repeats the same three steps and sentences in full
before dividing by \(1+2i\).

**given-in-step** (item, search). Step 3 of an A* exercise says "With
\(h(C) = 4\), the frontier value of \(C\) is \(g(C) + h(C)\)" and computes it.

**every-step-givens** (item, search). Each of five guide steps of the same exercise
opens by listing all six edge costs and all four heuristic values again.

**second-heuristic** (item, search). After misplaced tiles, the admissibility section
shows Manhattan distance on the same 8-puzzle state and why it never overestimates.

**bloch-opening** (item, quantum computing). Unit "Bloch sphere and phase" opens: the
normalized \(\lvert 0\rangle + \lvert 1\rangle\) and \(\lvert 0\rangle - \lvert
1\rangle\) point in opposite equatorial directions, and a common phase leaves the
direction unchanged. The next paragraph parameterizes the state with
\(\gamma, \theta, \varphi\). The sphere's figure comes three sections later.

**matrix-described** (item, quantum computing). "The diagonal matrix with entries 1, 0
keeps \(\lvert 0\rangle\) and removes \(\lvert 1\rangle\)." No matrix is shown.

**product-inner-compact** (item, quantum computing). "The tensor product states
\(\lvert 0\rangle\otimes\lvert +\rangle\) and \(\lvert 1\rangle\otimes\lvert +\rangle\) are
orthogonal: the first factors already have inner product zero. For product states,
\((\langle a\rvert\otimes\langle b\rvert)(\lvert c\rangle\otimes\lvert d\rangle)=\langle
a\mid c\rangle\langle b\mid d\rangle\). Extend the rule by linearity to sums."

**chain-rule-unpacked** (item, probability). "Both events happen when \(B\) happens and
then \(A\) happens given \(B\)." Points remind that \(P(A \mid B)\) is the probability
of \(A\) once \(B\) is known; a table works \(P(B) = 0.5\), \(P(A \mid B) = 0.4\), product
\(0.2\); then the formula block \(P(A \cap B) = P(A \mid B)\,P(B)\) with \(P(B) > 0\).

**reciprocal-without-rule** (item, quantum computing). The unit divides by \(1+2i\)
step by step and states \(z^*z = a^2+b^2\), but never gives
\(1/(a+bi) = (a-bi)/(a^2+b^2)\) or its condition \(a^2+b^2 > 0\).

The cases below calibrate how ideas are connected, in both directions: a move missing where
the content needs it, and a move forced where it does not ([teaching](../../prepare-study/references/teaching.md#teaching-moves)).

**abrupt-hmm** (item, probability). "Belief over time" opens: "A stochastic process is a
sequence of random variables over time." Stationarity and second-order chains follow before
the hidden Markov model is defined. Later sections start new examples ("Suppose initial rain
has probability 0.2"), and the filtering update uses a sensor likelihood of 0.8 where the
joint example used 0.9.

**related-hmm** (item, probability). The same unit opens: "You cannot see the weather, only
whether the director carries an umbrella." One umbrella world carries every example. The
filtering section opens: "Scoring one path is easy, but there are \(2^T\) of them, so keep one
belief and update it." Smoothing opens from filtering's limit: it ignores later evidence.

**signpost-filler** (item). "This section explains filtering. Moreover, filtering is very
important in practice."

**new-before-old** (item, quantum computing). "Towards the marked direction, by an angle
\(\theta\), the state is turned by each Grover iteration. Measurement squares the amplitude
it ends with, which is why the angle matters."

**fake-connective** (item, search). "BFS takes the oldest node from the frontier. Moreover,
DFS takes the newest. Furthermore, A* takes the one with the lowest estimate."

**term-switch** (item, search). One section calls the discovered but unexpanded nodes "the
frontier", the next paragraph "the open list" and its code comment "the queue".

**forced-bridge** (item, search). Three parallel sections give the frontier rule of BFS, DFS
and UCS; each opens "Now that we know the previous strategy, we need a new one."

**needless-worked-definition** (item, agents). The definition of a percept is followed by a
section "Worked example" with three numbered steps that apply it to a vacuum robot.

**hidden-insight** (item, search). The admissibility section names the term; its light-bulb
insight holds "it never overestimates the true remaining cost", which the practice needs.

**exam-reteaches** (course, Exam). The pattern "Compute a filtering step" opens with four
paragraphs that explain prediction and correction from scratch before its workflow.

**master-cases** (item, Exam pattern). The workflow's step 3 "Solve the recurrence" lists
three cases: \(d > \log_b a\) -> \(O(n^d)\), \(d = \log_b a\) -> \(O(n^d \log n)\),
\(d < \log_b a\) -> \(O(n^{\log_b a})\). Each case only names the final result.

**overlapping-limit-cases** (item, Exam pattern). A decision step on a limit lists "the
substitution gives a fraction" -> simplify, and "the substitution gives \(0/0\)" ->
L'Hopital. Every \(0/0\) example fits both cases.

**correct-only-feedback** (item, Exam pattern). Example 2 asks which case applies to
\(\lim_{x\to 1} \frac{x^2+1}{x-1}\); the feedback for the right case reads "Correct!" and
for the others "Wrong case."

**described-pitfall** (item, Exam pattern). Pitfalls: "Don't misuse L'Hopital." / "Use it
correctly." / "It is a common mistake."

**contextless-pitfall** (item, Exam pattern). Pitfall: "Step 2" / wrong \(P=\sin\varphi\) /
right \(P=\sin^2\varphi\) / "Measurement uses the squared magnitude." Nothing says what is
being computed when a student writes the wrong line.

**degenerate-fork** (item, Exam pattern). An estimation pattern's first step splits on
"the counts sum to more than zero" and "every count is zero"; no listed exam question has an
all-zero sample, yet the second case gets its own example and Practise item.

**merged-methods** (item, Exam pattern). A pattern's first step "Identify the requested
output and choose the matching branch" lists four cases, each a different calculation (build a
matrix from weights, expand a vector, reduce a joint state, apply a channel); step 2 reads
"Apply the selected operation".

**described-move** (item, Exam pattern). A decision step's case reads "the task asks for a
channel output" with the move "check their completeness and sum their action on the input",
and nothing opens under it; the completeness relation and the output formula appear only
in a worked example further down the page.

**bare-apply-formula** (item, Exam pattern). A workflow case opens to
\(\mathcal E(\rho)=\sum_j K_j\rho K_j^\dagger\) with no variable meanings; the Kraus operators
were defined two units earlier.

**underlined-indices** (item, any). A derivation marks \(i\), \(j\), \(n\) and \(\pi\) with
meanings such as "index" and "pi", next to an unexplained \(\rho_A\).

**echoed-meaning** (item, any). An applied formula's text reads "\(p_i\) is the probability of
the \(i\)-th state", and \(p_i\) in the formula opens the same meaning.

**generic-meaning** (item, Exercise). In a guide derivation for a sixteen-record search,
\(N\) opens "a number"; the task gives \(N=16\).

## Verdicts

| Case | Score | Check | Why |
| --- | --- | --- | --- |
| forward-heuristic | Course organization 2 | `organization.unit_order` | One unit uses a term a later unit teaches; teach the estimate first or define it in unit 2. |
| misc-group | Course organization 2 | `organization.categories` | "Misc" names no topic; the recap belongs with the unit that needs it. |
| short-lecture | Course organization 3 | `organization.categories` | Lecture groups follow the calendar; a short lecture may hold one unit. |
| course-folder | Course organization 2 | `organization.categories` | A folder around the whole course adds a level and helps no one find a unit. |
| retaught-in-exercise | Course redundancy 2; Integration 2 | `redundancy.exercises_link`; `integration.prerequisite_links` | The exercise teaches again instead of linking, and its link opens the unit, not the passage. |
| spaced-bfs | Course redundancy 3 | `redundancy.one_home` | Practice of one outcome in a new situation is spacing, not repetition. |
| table-retold | Redundancy 2 | `redundancy.text_restates_picture` | The paragraph reads the table aloud; it should say why the strategies differ. |
| tie-break-clash | Integration 1 | `integration.same_notation` | Two workspaces give different answers to the same tie; the student cannot tell which is right. |
| lecture-backbone | Course organization 3 | `organization.one_backbone` | Groups, dependencies and sheets follow one order. |
| pitfall-first | Organization 2 | `organization.builds_up`, `organization.outline` | The pitfall precedes its method, and "Overview", "More details" and "Notes" do not say what they teach. |
| recap-points | Redundancy 3 | `redundancy.said_once` | A closing recap of a few points supports recall; it is not repetition. |
| prereq-reminder | Redundancy 3; Cognitive load 3 | `cognitive_load.reminder_at_use` | A one-line reminder with a link to its home spares a return trip three units back; reinforcement. |
| conjugate-retaught | Redundancy 2 | `redundancy.said_once` | The same derivation in the same words twice; keep one home and remind in one line. |
| given-in-step | Redundancy 3 | `redundancy.no_repeated_labels` | The step restates the one given it uses, so it reads without scrolling back. |
| every-step-givens | Redundancy 2 | `redundancy.no_repeated_labels` | Every given in every step buries the new move; show the givens once and name the one each step uses. |
| second-heuristic | Redundancy 3; Intuition 3 | `redundancy.said_once` | A second example shows admissibility from another side; it is not a repeat. |
| bloch-opening | Cognitive load 2 | `cognitive_load.first_encounter` | Three new symbols and two new ideas before the student sees what the sphere depicts; orient first, picture early. |
| matrix-described | Representation 2 | `representation.shown_not_described` | The student must build the matrix from words; show \(\begin{pmatrix}1&0\\0&0\end{pmatrix}\) and say what it keeps. |
| product-inner-compact | Clarity 2 | `clarity.notation_unpacked` | The claim, four new symbols and the rule share two sentences; remind what a ket, \(\langle\cdot\mid\cdot\rangle\) and \(\otimes\) mean, work \(\langle 0\mid 1\rangle\langle +\mid +\rangle = 0\), then state the identity and its conjugate-linearity. |
| chain-rule-unpacked | Clarity 3; Redundancy 3 | `clarity.notation_unpacked` | Words, a local reminder, a worked case and then the rule; the reminder repeats a definition on purpose. |
| reciprocal-without-rule | Intuition 2 | `intuition.general_rule` | One worked number without its general formula and nonzero condition leaves the next case to guesswork. |
| abrupt-hmm | Intuition 2; Correctness 2 | `intuition.motivated`; `correctness.conventions` | Nothing says what problem the model solves, detours come before the model, and a given changes without notice. |
| related-hmm | Cohesion 3; Intuition 3 | `cohesion.linked` | Each section opens from the previous one's limit, so the order explains itself. |
| signpost-filler | Clarity 2 | `clarity.no_meta` | Both sentences talk about the page; neither says how filtering relates to anything. |
| new-before-old | Cohesion 2 | `cohesion.familiar_first`, `cohesion.point_first` | Each sentence opens on what is new and the point comes last; start from the iteration: "Each Grover iteration turns the state by \(\theta\)." |
| fake-connective | Cohesion 2 | `cohesion.honest_connectives` | The lines are parallel cases; "Moreover" fakes a relation. One table of frontier rules joins them. |
| term-switch | Cohesion 2 | `cohesion.one_term` | Three names make a reader expect three sets; keep "frontier". |
| forced-bridge | Cognitive load 2 | `cognitive_load.moves_fit` | Parallel cases do not follow from each other; a table or one framing line joins them. |
| needless-worked-definition | Cognitive load 2 | `cognitive_load.moves_fit` | A one-line definition has no interacting steps to work; one example or non-example is enough. |
| hidden-insight | Cognitive load 2 | `cognitive_load.moves_fit` | The defining condition is essential, so it belongs in the text, not behind a toggletip. |
| exam-reteaches | Course redundancy 2 | `redundancy.exam_compresses` | Exam revises; it should compress to the workflow and reach the lesson through Recall. |
| master-cases | Organization 2 | `organization.fork_placement` | The cases pick a final formula and change no move; the result table belongs in a cheatsheet entry reached through Recall, and the step says "compare \(d\) with \(\log_b a\)". |
| overlapping-limit-cases | Correctness 1 | `correctness.cases_exclusive` | A student who finds \(0/0\) cannot tell which move to make; split the cases by what substitution gives. |
| correct-only-feedback | Practice 2 | `practice.case_feedback` | The feedback never names the \(2/0\) that decides the case, so a wrong guess teaches nothing. |
| described-pitfall | Representation 2; Intuition 2 | `representation.shown_not_described`; `intuition.reasons` | No wrong working is shown and no rule says why it fails; show the \(2/0\) case and name the \(0/0\) condition. |
| contextless-pitfall | Representation 2 | `representation.shown_not_described` | A reader cannot tell when they would write \(\sin\varphi\); give the situation ("Turning the marked amplitude after \(k\) iterations into a success probability"). |
| degenerate-fork | Cognitive load 2 | `cognitive_load.moves_fit`, `coverage.cases_complete` | No exam reaches the invented case, which doubles the examples and practice; drop the fork and keep the edge as a pitfall if it costs marks. |
| merged-methods | Organization 2 | `organization.fork_placement` | The cases share no steps; they are four patterns behind one label, and "apply the selected operation" teaches no move. Split them and keep each workflow concrete. |
| described-move | Representation 2 | `representation.shown_not_described` | The move names a formula the student must recall elsewhere; give the case an `apply` with \(\sum_j K_j^\dagger K_j=I\) and \(\mathcal E(\rho)=\sum_j K_j\rho K_j^\dagger\). |
| bare-apply-formula | Clarity 2 | `clarity.symbols_recall` | A required meaning is missing where the student must recall the Kraus operators; give \(K_j\) its meaning in this pattern. |
| underlined-indices | Cognitive load 2 | `clarity.symbols_recall` | Marks on obvious indices and constants hide the one variable that needed a meaning; mark \(\rho_A\) only. |
| echoed-meaning | Redundancy 2 | `redundancy.said_once` | The meaning is said twice; drop it from the text and keep it on the formula. |
| generic-meaning | Clarity 2 | `clarity.symbols_recall` | The meaning names no role or value; write "records in the database, 16 here". |
