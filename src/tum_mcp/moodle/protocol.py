from jsonschema import ValidationError, validate
from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, InputRequiredResult, Tool
from pydantic import JsonValue


def _argument_problem(error: ValidationError, schema: dict, arguments: dict) -> str:
    """Name the offending fields without echoing any supplied value."""
    accepted = sorted(schema.get("properties", {}))
    if error.validator == "additionalProperties" and not error.absolute_path:
        unexpected = sorted(set(arguments) - set(accepted))
        return f"unexpected {', '.join(unexpected)}; accepted: {', '.join(accepted) or 'none'}"
    if error.validator == "required" and not error.absolute_path:
        missing = [key for key in schema.get("required", ()) if key not in arguments]
        return f"missing {', '.join(missing)}"
    field = ".".join(str(part) for part in error.absolute_path) or "arguments"
    return f"{field} fails its {error.validator} rule"


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
                except ValidationError as error:
                    problem = _argument_problem(error, tool.input_schema, arguments)
                    raise ToolError(f"Invalid arguments for {name}: {problem}.") from None
                break
        return await super().call_tool(name, arguments, context)
