// The synthetic "Graph Search" course: the source snapshot the walkthrough's course is built from.
// Every resource is invented for the walkthrough and marked synthetic; no campus material is used.

const binding = 'synthetic';
const source = (key, kind, title, locator, text) => ({
  key, binding, kind, title, url: `https://example.invalid/graph-search/${key}`, locator, revision: '1', text,
});

const lecture1 = `# Lecture 1 · Breadth-first search (synthetic)

Slide 2 · Graphs. A graph G = (V, E) has vertices V and edges E. In an unweighted graph every edge counts as one step. The distance d(s, v) is the least number of edges on a path from s to v.

Slide 4 · Running example. Vertices S, A, B, C, D, E, G. Edges: S–A, S–B, S–E, A–C, B–C, B–D, C–G, D–G. All edges are undirected.

Slide 6 · Layers. Breadth-first search (BFS) from s visits vertices in layers: layer 0 is s, layer k + 1 holds the undiscovered neighbours of layer k. In the running example: layer 0 = {S}, layer 1 = {A, B, E}, layer 2 = {C, D}, layer 3 = {G}.

Slide 8 · Queue discipline. BFS keeps a FIFO queue. It removes the front vertex u and appends every undiscovered neighbour v with d(v) = d(u) + 1 and parent(v) = u. Because the queue is first-in first-out, every vertex of layer k leaves the queue before any vertex of layer k + 1.

Slide 9 · Mark when you enqueue. A vertex is marked discovered when it is appended, not when it is removed. Marking on removal lets the same vertex enter the queue twice: in the running example C would be appended by A and again by B.

Slide 11 · Result. When BFS finishes, d(v) is the shortest edge count from s, and following parent pointers back from v gives one shortest path. Running time O(|V| + |E|) with adjacency lists.

Slide 12 · Limits. BFS minimises the number of edges, not the total weight. With edge weights it can return a path that is longer in total cost.`;

const lecture2 = `# Lecture 2 · Dijkstra's algorithm (synthetic)

Slide 2 · Weighted graphs. Each edge (u, v) has a weight w(u, v) ≥ 0. The distance d(s, v) is the least total weight of a path from s to v.

Slide 3 · Running example with weights. S–A 2, S–B 6, S–E 1, A–C 2, B–C 1, B–D 2, C–G 5, D–G 1. Undirected.

Slide 5 · Relaxation. For an edge (u, v), relaxation sets d(v) ← min(d(v), d(u) + w(u, v)) and records u as the parent of v when the value decreases.

Slide 7 · The algorithm. Start with d(s) = 0 and d(v) = ∞ otherwise. Repeat: choose the unsettled vertex u with the smallest d(u), settle it, and relax every edge leaving u. A priority queue keyed by d returns u.

Slide 8 · Trace from S. Settle S (0): A = 2, B = 6, E = 1. Settle E (1): no change. Settle A (2): C = 4. Settle C (4): B = 5 (improved from 6), G = 9. Settle B (5): D = 7. Settle D (7): G = 8 (improved from 9). Settle G (8). Shortest path to G: S, A, C, B, D, G with cost 8.

Slide 9 · Why it is correct. When u has the smallest tentative distance, any other path to u must leave the settled set through a vertex whose tentative distance is at least d(u); with non-negative weights it cannot end below d(u). So a settled distance never changes.

Slide 10 · Negative weights. The argument needs w ≥ 0. With a negative edge a settled distance can later be undercut, and Dijkstra may return a wrong distance.

Slide 11 · Cost. With a binary heap: O((|V| + |E|) log |V|).

Slide 12 · Compare with BFS. BFS on the same graph, appending neighbours alphabetically, reaches G by S, A, C, G (3 edges, cost 9). Dijkstra finds S, A, C, B, D, G (5 edges, cost 8).`;

const lecture3 = `# Lecture 3 · A* search (synthetic)

Slide 2 · Idea. Dijkstra explores in all directions. A* adds an estimate h(v) of the remaining cost from v to the goal and expands by f(v) = g(v) + h(v), where g(v) is the best known cost from s.

Slide 4 · Heuristic for the running example (goal G). h(S) = 7, h(A) = 5, h(B) = 3, h(C) = 3, h(D) = 1, h(E) = 8, h(G) = 0.

Slide 5 · Admissible. A heuristic is admissible when h(v) ≤ d(v, goal) for every v: it never overestimates. With an admissible heuristic, A* returns an optimal path.

Slide 6 · Consistent. A heuristic is consistent when h(u) ≤ w(u, v) + h(v) for every edge (u, v) and h(goal) = 0. Consistency implies admissibility, and with it A* never needs to reopen a vertex.

Slide 8 · Trace from S. Open: S (g 0, f 7). Expand S: A (2, 7), B (6, 9), E (1, 9). Expand A: C (4, 7). Expand C: B improves to (5, 8), G (9, 9). Expand B: D (7, 8). Expand D: G improves to (8, 8). Expand G: done, cost 8. E is never expanded.

Slide 9 · Effect. Dijkstra settles all seven vertices; A* expands six and skips E, whose f = 9 exceeds the optimal cost 8.

Slide 10 · Overestimation. If h(v) is larger than the true remaining cost, A* can stop with a path that is not optimal.

Slide 11 · Special cases. With h = 0, A* behaves like Dijkstra.`;

const recording = `Synthetic lecture recording · Lecture 2 · Dijkstra's algorithm (12:00)

0:00–1:10 Recap: BFS counts edges. On the running example it reaches G by S, A, C, G, three edges but cost 9.
1:10–3:40 Relaxation on the board. Edge S–B with weight 6 gives B the tentative distance 6. Later the path through C offers 4 + 1 = 5, so relaxation lowers B to 5 and changes its parent to C.
3:40–7:30 Full trace on the board, settling S, E, A, C, B, D, G. The lecturer writes the tentative distances in a table after each step and circles each settled value. Board frame at 6:05 shows the table after settling C.
7:30–9:45 Why a settled distance never changes: the smallest tentative distance cannot be undercut when weights are non-negative. The lecturer draws the settled set as a region and a path leaving it. Board frame at 8:20.
9:45–11:20 Counterexample with a negative edge: three vertices, S–X 2, S–Y 3, Y–X −2. Dijkstra settles X at 2 although the path through Y costs 1. Board frame at 10:30.
11:20–12:00 Organisation: exercise sheet 2 is released; questions in the forum.`;

const sheet = `# Exercise sheet 1 · Graph search (synthetic)

Exercise 1 · BFS layers. Graph: P–Q, P–R, Q–T, R–T, R–U, T–V, U–V. Run BFS from P. (a) Give d(v) for every vertex. (b) Give the parent of every vertex when neighbours are appended in alphabetical order. (c) Explain why T is appended only once.

Exercise 2 · Dijkstra trace. Weighted undirected graph: P–Q 4, P–R 1, R–Q 2, Q–T 1, R–T 5, T–V 3. Run Dijkstra from P. (a) Fill in a table of tentative distances after each settled vertex. (b) Give the shortest path to V and its cost.

Exercise 3 · Heuristics. For the running example of lecture 3, decide for each change whether h stays admissible: (a) h(B) = 4, (b) h(D) = 0, (c) h(A) = 6.`;

const pastPaper = `# Past paper · Graph Search · Synthetic exam (60 minutes, 24 points)

Question 1 (6 points). Run BFS from S on the graph S–A, S–B, A–C, B–C, C–D. Give the distance and parent of every vertex.

Question 2 (8 points). Run Dijkstra from S on S–A 4, S–B 1, B–A 2, A–C 1, B–C 5. Give the table of tentative distances after each settled vertex and the shortest path to C.

Question 3 (4 points). Give a graph with one negative edge on which Dijkstra returns a wrong distance, and name the step that goes wrong.

Question 4 (6 points). A heuristic satisfies h(u) ≤ w(u, v) + h(v) for every edge and h(goal) = 0. Show that it is admissible.`;

export const snapshot = {
  schema_version: 1,
  course: {
    key: 'graph-search',
    title: 'Graph Search',
    semester: 'Synthetic course',
    synthetic: true,
    bindings: [{ key: binding, provider: 'sample', course_id: 'graph-search' }],
  },
  coverage: [{ binding, status: 'complete', checked_at: '2026-11-10T09:00:00Z', note: 'Synthetic sources written for the TUM MCP walkthrough.' }],
  resources: [
    source('lecture-01', 'content', 'Lecture 1 · Breadth-first search', 'Slides 1–12', lecture1),
    source('lecture-02', 'content', "Lecture 2 · Dijkstra's algorithm", 'Slides 1–12', lecture2),
    source('lecture-03', 'content', 'Lecture 3 · A* search', 'Slides 1–11', lecture3),
    source('recording-02', 'content', "Recording · Lecture 2 · Dijkstra's algorithm", '0:00–12:00 transcript; board 6:05, 8:20, 10:30', recording),
    source('sheet-01', 'exercise', 'Exercise sheet 1 · Graph search', 'Exercises 1–3', sheet),
    source('past-paper', 'exam', 'Past paper · Synthetic exam', 'Questions 1–4', pastPaper),
  ],
};
