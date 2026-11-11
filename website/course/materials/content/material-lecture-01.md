# Lecture 1 · Breadth-first search (synthetic)

Slide 2 · Graphs. A graph G = (V, E) has vertices V and edges E. In an unweighted graph every edge counts as one step. The distance d(s, v) is the least number of edges on a path from s to v.

Slide 4 · Running example. Vertices S, A, B, C, D, E, G. Edges: S–A, S–B, S–E, A–C, B–C, B–D, C–G, D–G. All edges are undirected.

Slide 6 · Layers. Breadth-first search (BFS) from s visits vertices in layers: layer 0 is s, layer k + 1 holds the undiscovered neighbours of layer k. In the running example: layer 0 = {S}, layer 1 = {A, B, E}, layer 2 = {C, D}, layer 3 = {G}.

Slide 8 · Queue discipline. BFS keeps a FIFO queue. It removes the front vertex u and appends every undiscovered neighbour v with d(v) = d(u) + 1 and parent(v) = u. Because the queue is first-in first-out, every vertex of layer k leaves the queue before any vertex of layer k + 1.

Slide 9 · Mark when you enqueue. A vertex is marked discovered when it is appended, not when it is removed. Marking on removal lets the same vertex enter the queue twice: in the running example C would be appended by A and again by B.

Slide 11 · Result. When BFS finishes, d(v) is the shortest edge count from s, and following parent pointers back from v gives one shortest path. Running time O(|V| + |E|) with adjacency lists.

Slide 12 · Limits. BFS minimises the number of edges, not the total weight. With edge weights it can return a path that is longer in total cost.