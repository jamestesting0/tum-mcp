import io
import json
import subprocess
import sys
import textwrap

from skill_lab import mcp_proxy, paths

FAKE_SERVER = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("method") == "tools/list":
            tools = [
                {"name": "moodle_list_courses"},
                {"name": "tum_logout"},
                {"name": "wipe", "annotations": {"destructiveHint": True}},
            ]
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": {"tools": tools}}
        else:
            name = message["params"]["name"]
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": {"called": name}}
        print(json.dumps(reply), flush=True)
    """
)


def request(identifier, method, name=None):
    message = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if name:
        message["params"] = {"name": name, "arguments": {}}
    return json.dumps(message)


def test_proxy_filters_the_tool_list_and_refuses_blocked_calls(tmp_path):
    server = tmp_path / "server.py"
    server.write_text(FAKE_SERVER)
    proxy = paths.LAB / "skill_lab" / "mcp_proxy.py"
    lines = [
        request(1, "tools/list"),
        request(2, "tools/call", "tum_logout"),
        request(3, "tools/call", "moodle_list_courses"),
    ]
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(proxy),
            "--block",
            "tum_logout",
            "--",
            sys.executable,
            "-I",
            str(server),
        ],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    replies = {m["id"]: m for m in map(json.loads, completed.stdout.splitlines())}
    names = [tool["name"] for tool in replies[1]["result"]["tools"]]
    assert names == ["moodle_list_courses"]
    assert replies[2]["result"]["isError"] is True
    assert replies[3]["result"] == {"called": "moodle_list_courses"}


def test_destructive_tools_seen_in_a_list_are_refused_afterwards():
    out = io.StringIO()
    proxy = mcp_proxy.Proxy({"tum_logout"}, out)
    assert proxy.from_client(request(1, "tools/list")) is not None
    listed = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"tools": [{"name": "wipe", "annotations": {"destructiveHint": True}}]},
    }
    assert json.loads(proxy.from_server(json.dumps(listed)))["result"]["tools"] == []
    assert proxy.from_client(request(2, "tools/call", "wipe")) is None
    assert json.loads(out.getvalue())["result"]["isError"] is True
