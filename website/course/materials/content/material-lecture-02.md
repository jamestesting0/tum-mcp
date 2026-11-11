# Lecture 2 · Dijkstra's algorithm (synthetic)

Slide 2 · Weighted graphs. Each edge (u, v) has a weight w(u, v) ≥ 0. The distance d(s, v) is the least total weight of a path from s to v.

Slide 3 · Running example with weights. S–A 2, S–B 6, S–E 1, A–C 2, B–C 1, B–D 2, C–G 5, D–G 1. Undirected.

Slide 5 · Relaxation. For an edge (u, v), relaxation sets d(v) ← min(d(v), d(u) + w(u, v)) and records u as the parent of v when the value decreases.

Slide 7 · The algorithm. Start with d(s) = 0 and d(v) = ∞ otherwise. Repeat: choose the unsettled vertex u with the smallest d(u), settle it, and relax every edge leaving u. A priority queue keyed by d returns u.

Slide 8 · Trace from S. Settle S (0): A = 2, B = 6, E = 1. Settle E (1): no change. Settle A (2): C = 4. Settle C (4): B = 5 (improved from 6), G = 9. Settle B (5): D = 7. Settle D (7): G = 8 (improved from 9). Settle G (8). Shortest path to G: S, A, C, B, D, G with cost 8.

Slide 9 · Why it is correct. When u has the smallest tentative distance, any other path to u must leave the settled set through a vertex whose tentative distance is at least d(u); with non-negative weights it cannot end below d(u). So a settled distance never changes.

Slide 10 · Negative weights. The argument needs w ≥ 0. With a negative edge a settled distance can later be undercut, and Dijkstra may return a wrong distance.

Slide 11 · Cost. With a binary heap: O((|V| + |E|) log |V|).

Slide 12 · Compare with BFS. BFS on the same graph, appending neighbours alphabetically, reaches G by S, A, C, G (3 edges, cost 9). Dijkstra finds S, A, C, B, D, G (5 edges, cost 8).