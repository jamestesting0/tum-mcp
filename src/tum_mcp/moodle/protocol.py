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
    if error.validator in {"minimum", "maximum"}:
        bound = error.validator_value
        if isinstance(bound, int | float):
            direction = "at least" if error.validator == "minimum" else "at most"
            return f"{field} must be {direction} {bound}"
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
                    if name in {"moodle_list_courses", "moodle_list_materials"} and (
                        tuple(error.absolute_path) == ("limit",)
                    ):
                        problem += (
                            ". Omit limit to use the default, then pass each returned "
                            "next_cursor as cursor with the same filters until it is absent"
                        )
                    raise ToolError(f"Invalid arguments for {name}: {problem}.") from None
                break
        return await super().call_tool(name, arguments, context)
