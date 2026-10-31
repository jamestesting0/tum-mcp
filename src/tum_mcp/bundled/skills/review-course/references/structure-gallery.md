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
