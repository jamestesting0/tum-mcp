# Teaching review · 01_dijkstra-s-algorithm

Reviewed against Study unit dijkstra (blocks 1–5, objectives relax, trace, negative) on 2026-11-11.

- Coverage: relaxation (formula block), the settle loop and full trace (walkthrough), the settled-distance argument and the negative-edge pitfall; the BFS comparison table is left to the lesson.
- Fidelity: every number matches the unit: B 6 → 5 through C, G 9 → 8 through D, settle order S, E, A, C, B, D, G; counterexample 2, 3, −2 with true cost 1.
- Reasoning: each step names why the next vertex is chosen (smallest open value) and why the negative edge fails (a settled value is final).
- Referents: narration names the vertex and number on screen ("vertex C is settled at four"); nothing relies on colour alone (labels "Settled at 2", "True cost 1").
- Orientation and ending: the opening names the two moves; the recap restates the loop and its condition.
- Visual review: contact sheets of draft r-85ce1376 and final r-05b304e3 inspected; the chapter 3 graph and table were enlarged after the draft.
