# Lecture 3 · A* search (synthetic)

Slide 2 · Idea. Dijkstra explores in all directions. A* adds an estimate h(v) of the remaining cost from v to the goal and expands by f(v) = g(v) + h(v), where g(v) is the best known cost from s.

Slide 4 · Heuristic for the running example (goal G). h(S) = 7, h(A) = 5, h(B) = 3, h(C) = 3, h(D) = 1, h(E) = 8, h(G) = 0.

Slide 5 · Admissible. A heuristic is admissible when h(v) ≤ d(v, goal) for every v: it never overestimates. With an admissible heuristic, A* returns an optimal path.

Slide 6 · Consistent. A heuristic is consistent when h(u) ≤ w(u, v) + h(v) for every edge (u, v) and h(goal) = 0. Consistency implies admissibility, and with it A* never needs to reopen a vertex.

Slide 8 · Trace from S. Open: S (g 0, f 7). Expand S: A (2, 7), B (6, 9), E (1, 9). Expand A: C (4, 7). Expand C: B improves to (5, 8), G (9, 9). Expand B: D (7, 8). Expand D: G improves to (8, 8). Expand G: done, cost 8. E is never expanded.

Slide 9 · Effect. Dijkstra settles all seven vertices; A* expands six and skips E, whose f = 9 exceeds the optimal cost 8.

Slide 10 · Overestimation. If h(v) is larger than the true remaining cost, A* can stop with a path that is not optimal.

Slide 11 · Special cases. With h = 0, A* behaves like Dijkstra.