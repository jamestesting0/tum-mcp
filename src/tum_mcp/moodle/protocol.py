from jsonschema import ValidationError, validate
from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, InputRequiredResult, Tool
from pydantic import JsonValue


class StrictMCPServer(MCPServer):
    async def list_tools(self) -> list[Tool]:
        return [
            tool.model_copy(
                update={
                    "input_schema": {
                        **tool.input_schema,
                        "additionalProperties": False,
                    }
                }
            )
            for tool in await super().list_tools()
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, JsonValue],
        context: Context[None, None] | None = None,
    ) -> CallToolResult | InputRequiredResult:
        for tool in await self.list_tools():
            if tool.name == name:
                try:
                    validate(arguments, tool.input_schema)
                except ValidationError:
                    raise ToolError(f"Invalid arguments for {name}.") from None
                break
        return await super().call_tool(name, arguments, context)
