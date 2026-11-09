"""Deterministic semester-map layout: topic regions in course order, derivation depth rows."""

from collections import defaultdict
from functools import partial

from pydantic import JsonValue

from tum_mcp.course.content.exam import ExamContent

NODE_WIDTH, NODE_HEIGHT = 160, 56
NODE_GAP, ROW_GAP = 16, 40
# Each topic is a region (group-in-a-box): its title centred in a header band over its ideas.
REGION_PADDING, REGION_HEADER, REGION_FOOTER, REGION_GAP = 16, 44, 24, 48
# Regions flow in course order and wrap at this width, so the opening view reads at full size.
ROW_WIDTH = 860
PADDING = 16
SWEEPS = 8
PER_ROW = 2


def layout(content: ExamContent) -> dict[str, JsonValue]:
    """Lay out on-map concepts; identical content always yields identical coordinates."""
    nodes = {concept.key: concept for concept in content.concepts if concept.on_map}
    # Ideas keep the cheatsheet's order inside a cell, so the map reads like the sheet.
    order = {key: index for index, key in enumerate(nodes)}
    if not nodes:
        return {"width": 0, "height": 0, "regions": [], "nodes": [], "edges": [], "overview": {}}
    topics = sorted(
        (topic for topic in content.topics if any(n.topic == topic.key for n in nodes.values())),
        key=lambda topic: (topic.order, topic.key),
    )
    links = [link for link in content.links if link.start in nodes and link.end in nodes]
    # Depth counts only links within a topic, so each region reads top-down on its own;
    # links across topics run between regions.
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
    region_of = {topic.key: index for index, topic in enumerate(topics)}
    titles = [topic.title for topic in topics]
    for key in nodes:
        cells[(region_of[nodes[key].topic], depth[key])].append(key)
    for _ in range(SWEEPS):
        position = _place(cells, titles)[0]
        for cell in sorted(cells):
            cells[cell] = sorted(cells[cell], key=partial(_barycentre, position, neighbours, order))
            # A band that wraps puts the ideas that lead further down in its last row, so their
            # arrows reach the next band without passing another card.
            if len(cells[cell]) > PER_ROW:
                cells[cell].sort(key=lambda key: bool(following[key]))
    position, top, boxes, total_width, total_height = _place(cells, titles)
    placed = [
        {
            "key": key,
            "x": round(position[key] - NODE_WIDTH / 2),
            "y": top[key],
            "column": region_of[nodes[key].topic],
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
        "header": REGION_HEADER,
        "gap": REGION_GAP,
        "regions": [
            {"topic": topic.key, "title": topic.title, **boxes[index]}
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
    cells: dict[tuple[int, int], list[str]], titles: list[str]
) -> tuple[dict[str, float], dict[str, int], list[dict[str, int]], int, int]:
    """Centre x and top y per node and each region's box; a depth band wraps after PER_ROW
    nodes, and regions, each as tall as its ideas, wrap into top-aligned rows at ROW_WIDTH."""
    regions = len(titles)
    bands = [
        sorted(depth for (index, depth) in cells if index == region) for region in range(regions)
    ]
    slots = [
        max((min(PER_ROW, len(cells[(region, band)])) for band in bands[region]), default=1)
        for region in range(regions)
    ]
    lines = [
        sum(-(-len(cells[(region, band)]) // PER_ROW) for band in bands[region])
        for region in range(regions)
    ]
    # A region is at least as wide as its title (about 7.6 px a character at 14 px).
    widths = [
        max(slots[region] * NODE_WIDTH + (slots[region] - 1) * NODE_GAP, round(len(title) * 7.6))
        + 2 * REGION_PADDING
        for region, title in enumerate(titles)
    ]
    heights = [
        REGION_HEADER + lines[region] * NODE_HEIGHT + (lines[region] - 1) * ROW_GAP + REGION_FOOTER
        for region in range(regions)
    ]
    rows: list[list[int]] = [[]]
    for region in range(regions):
        used = sum(widths[index] for index in rows[-1]) + REGION_GAP * len(rows[-1])
        if rows[-1] and used + widths[region] > ROW_WIDTH:
            rows.append([])
        rows[-1].append(region)
    span = max(sum(widths[index] for index in row) + REGION_GAP * (len(row) - 1) for row in rows)
    boxes: list[dict[str, int]] = [{} for _ in range(regions)]
    y = PADDING
    for row in rows:
        height = max(heights[index] for index in row)
        x = PADDING + (span - sum(widths[i] for i in row) - REGION_GAP * (len(row) - 1)) // 2
        for index in row:
            boxes[index] = {"x": x, "y": y, "width": widths[index], "height": heights[index]}
            x += widths[index] + REGION_GAP
        y += height + REGION_GAP
    position: dict[str, float] = {}
    top: dict[str, int] = {}
    for region in range(regions):
        box = boxes[region]
        inner = box["width"] - 2 * REGION_PADDING
        y = box["y"] + REGION_HEADER
        for band in bands[region]:
            keys = cells[(region, band)]
            for row in range(0, len(keys), PER_ROW):
                chunk = keys[row : row + PER_ROW]
                used = len(chunk) * NODE_WIDTH + (len(chunk) - 1) * NODE_GAP
                left = box["x"] + REGION_PADDING + (inner - used) / 2
                for index, key in enumerate(chunk):
                    position[key] = left + index * (NODE_WIDTH + NODE_GAP) + NODE_WIDTH / 2
                    top[key] = y
                y += NODE_HEIGHT + ROW_GAP
    bottom = max(box["y"] + box["height"] for box in boxes)
    return position, top, boxes, span + 2 * PADDING, bottom + PADDING


def _barycentre(
    position: dict[str, float], neighbours: dict[str, set[str]], order: dict[str, int], key: str
) -> tuple[float, int]:
    around = [position[other] for other in neighbours[key]]
    return (sum(around) / len(around) if around else position[key], order[key])


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
