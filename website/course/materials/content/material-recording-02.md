Synthetic lecture recording · Lecture 2 · Dijkstra's algorithm (12:00)

0:00–1:10 Recap: BFS counts edges. On the running example it reaches G by S, A, C, G, three edges but cost 9.
1:10–3:40 Relaxation on the board. Edge S–B with weight 6 gives B the tentative distance 6. Later the path through C offers 4 + 1 = 5, so relaxation lowers B to 5 and changes its parent to C.
3:40–7:30 Full trace on the board, settling S, E, A, C, B, D, G. The lecturer writes the tentative distances in a table after each step and circles each settled value. Board frame at 6:05 shows the table after settling C.
7:30–9:45 Why a settled distance never changes: the smallest tentative distance cannot be undercut when weights are non-negative. The lecturer draws the settled set as a region and a path leaving it. Board frame at 8:20.
9:45–11:20 Counterexample with a negative edge: three vertices, S–X 2, S–Y 3, Y–X −2. Dijkstra settles X at 2 although the path through Y costs 1. Board frame at 10:30.
11:20–12:00 Organisation: exercise sheet 2 is released; questions in the forum.