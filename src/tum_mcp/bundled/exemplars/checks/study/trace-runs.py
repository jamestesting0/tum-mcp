"""Example answer-key shape for a two-run graph walkthrough."""

import json


def run(start: str) -> list[dict[str, str | dict[str, str]]]:
    return [
        {"Frontier": start, "@node_values": {start.lower(): "0"}},
        {"Frontier": "G", "@node_values": {start.lower(): "0", "g": "1"}},
    ]


print(
    json.dumps(
        {
            "values": {"blocks[0].result": 1},
            "walkthroughs": {"trace": {"primary": run("S"), "variant": run("A")}},
        }
    )
)
