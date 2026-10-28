"""Deterministic semester-map layout: topic columns, derivation depth rows, few crossings."""

from collections import defaultdict
from functools import partial

from pydantic import JsonValue

from tum_mcp.exam_content import ExamContent

NODE_WIDTH, NODE_HEIGHT = 160, 56
NODE_GAP, COLUMN_GAP, ROW_GAP = 16, 48, 40
PADDING, HEADER = 20, 44
SWEEPS = 8
PER_ROW = 2


def layout(content: ExamContent) -> dict[str, JsonValue]:
    """Lay out on-map concepts; identical content always yields identical coordinates."""
    nodes = {concept.key: concept for concept in content.concepts if concept.on_map}
    if not nodes:
        return {"width": 0, "height": 0, "columns": [], "nodes": [], "edges": [], "overview": {}}
    topics = sorted(
        (topic for topic in content.topics if any(n.topic == topic.key for n in nodes.values())),
        key=lambda topic: (topic.order, topic.key),
    )
    links = [link for link in content.links if link.start in nodes and link.end in nodes]
    # Depth counts only links within a topic, so each column reads top-down on its
    # own; links across topics are drawn side to side between columns.
    following: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link.kind != "contrasts" and nodes[link.start].topic == nodes[link.end].topic:
            following[link.start].append(link.end)
    depth = _depths(sorted(nodes), following)
    neighbours: dict[str, set[str]] = defaultdict(set)
    for link in links:
        neighbours[link.start].add(link.end)
        neighbours[link.end].add(link.start)
    cells: dict[tuple[int, int], list[str]] = defaultdict(list)
    column_of = {topic.key: index for index, topic in enumerate(topics)}
    for key in sorted(nodes):
        cells[(column_of[nodes[key].topic], depth[key])].append(key)
    for _ in range(SWEEPS):
        position = _place(cells, len(topics))[0]
        for cell in sorted(cells):
            cells[cell] = sorted(cells[cell], key=partial(_barycentre, position, neighbours))
    position, rows_y, widths, starts, total_width, total_height = _place(cells, len(topics))
    placed = [
        {
            "key": key,
            "x": round(position[key] - NODE_WIDTH / 2),
            "y": rows_y[key],
            "column": column_of[nodes[key].topic],
            "depth": depth[key],
        }
        for key in sorted(nodes)
    ]
    cross: dict[tuple[str, str], int] = defaultdict(int)
    for link in links:
        left, right = nodes[link.start].topic, nodes[link.end].topic
        if left != right:
            cross[tuple(sorted((left, right)))] += 1
    return {
        "width": total_width,
        "height": total_height,
        "node_width": NODE_WIDTH,
        "node_height": NODE_HEIGHT,
        "columns": [
            {
                "topic": topic.key,
                "title": topic.title,
                "x": starts[index],
                "width": widths[index] * NODE_WIDTH + (widths[index] - 1) * NODE_GAP,
            }
            for index, topic in enumerate(topics)
        ],
        "nodes": placed,
        "edges": [{"start": link.start, "end": link.end, "kind": link.kind} for link in links],
        "overview": {
            "topics": [
                {
                    "topic": topic.key,
                    "concepts": sum(node.topic == topic.key for node in nodes.values()),
                }
                for topic in topics
            ],
            "links": [
                {"start": left, "end": right, "count": count}
                for (left, right), count in sorted(cross.items())
            ],
        },
    }


def _place(
    cells: dict[tuple[int, int], list[str]], columns: int
) -> tuple[dict[str, float], dict[str, int], list[int], list[int], int, int]:
    """Centre x and top y per node; a depth band wraps after PER_ROW nodes."""
    widths = [
        max(
            (min(PER_ROW, len(keys)) for (column, _), keys in cells.items() if column == index),
            default=1,
        )
        for index in range(columns)
    ]
    starts, cursor = [], PADDING
    for width in widths:
        starts.append(cursor)
        cursor += width * NODE_WIDTH + (width - 1) * NODE_GAP + COLUMN_GAP
    position: dict[str, float] = {}
    top: dict[str, int] = {}
    bottom = PADDING + HEADER
    for column in range(columns):
        y = PADDING + HEADER
        span = widths[column] * NODE_WIDTH + (widths[column] - 1) * NODE_GAP
        for band in sorted(depth for (index, depth) in cells if index == column):
            keys = cells[(column, band)]
            for row in range(0, len(keys), PER_ROW):
                chunk = keys[row : row + PER_ROW]
                used = len(chunk) * NODE_WIDTH + (len(chunk) - 1) * NODE_GAP
                left = starts[column] + (span - used) / 2
                for index, key in enumerate(chunk):
                    position[key] = left + index * (NODE_WIDTH + NODE_GAP) + NODE_WIDTH / 2
                    top[key] = y
                y += NODE_HEIGHT + ROW_GAP
        bottom = max(bottom, y - ROW_GAP)
    return position, top, widths, starts, cursor - COLUMN_GAP + PADDING, bottom + PADDING


def _barycentre(
    position: dict[str, float], neighbours: dict[str, set[str]], key: str
) -> tuple[float, str]:
    around = [position[other] for other in neighbours[key]]
    return (sum(around) / len(around) if around else position[key], key)


def _depths(keys: list[str], following: dict[str, list[str]]) -> dict[str, int]:
    """Longest path from a foundation; links are validated acyclic before layout."""
    incoming: dict[str, int] = {key: 0 for key in keys}
    for start in keys:
        for end in following[start]:
            incoming[end] += 1
    depth = {key: 0 for key in keys}
    ready = sorted(key for key, count in incoming.items() if count == 0)
    while ready:
        key = ready.pop(0)
        for end in sorted(following[key]):
            depth[end] = max(depth[end], depth[key] + 1)
            incoming[end] -= 1
            if incoming[end] == 0:
                ready.append(end)
        ready.sort()
    return depth
