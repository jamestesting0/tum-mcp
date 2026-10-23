import json
import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tum_moodle.auth import system_keyring
from tum_moodle.errors import MoodleError


async def check() -> None:
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "tum_moodle", "serve"])
    with anyio.fail_after(25):
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                required = {
                    "moodle_auth_status",
                    "moodle_login",
                    "moodle_list_courses",
                    "moodle_read_material",
                    "moodle_download_material",
                }
                if not required <= {tool.name for tool in tools.tools}:
                    raise RuntimeError("The runtime is missing required Moodle tools.")
    keyring_error = None
    try:
        system_keyring()
    except MoodleError as error:
        keyring_error = error.message
    print(
        json.dumps(
            {
                "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                "tools": len(tools.tools),
                "keyring_error": keyring_error,
            }
        )
    )


if __name__ == "__main__":
    anyio.run(check)
