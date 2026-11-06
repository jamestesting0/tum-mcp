"""Answer key for study/bfs: run breadth-first search on the walkthrough's graph and print
the frontier and expanded nodes after each step, as the walkthrough must show them."""

import json
from collections import deque

EDGES = {"S": "AB", "A": "SC", "B": "SG", "C": "AG", "G": "BC"}
GOAL = "G"


def trace() -> list[dict[str, str]]:
    frontier, found, expanded, parent = deque("S"), {"S"}, [], {}
    states = [{"Frontier": "S", "Expanded": "none"}]
    while frontier:
        node = frontier.popleft()
        expanded.append(node)
        for neighbour in EDGES[node]:
            if neighbour in found:
                continue
            found.add(neighbour)
            parent[neighbour] = node
            frontier.append(neighbour)
            if neighbour == GOAL:
                path = [GOAL]
                while path[-1] != "S":
                    path.append(parent[path[-1]])
                states.append({"Frontier": ", ".join(frontier), "Expanded": ", ".join(expanded)})
                route = r" \to ".join(reversed(path))
                states.append({"Frontier": ", ".join(frontier), "Path": rf"\({route}\)"})
                return states
        states.append({"Frontier": ", ".join(frontier), "Expanded": ", ".join(expanded)})
    return states


print(json.dumps({"walkthroughs": {"bfs-trace": trace()}}))
