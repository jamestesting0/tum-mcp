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
