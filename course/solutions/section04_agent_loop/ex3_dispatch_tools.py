"""Exercise 4.3 -- Run the tools the model asked for.

Lecture: 4.3 "end_turn and tool_use: the happy path"

Given the ``tool_use`` blocks from one turn, run each one and return a list of
``tool_result`` blocks -- one per call, in the same order. A failure in one
tool must never stop the run; it becomes an error result the model can read.

For each block (``.id``, ``.name``, ``.input``):

* unknown tool -> error result naming the tool **and** listing the available
  tool names, so the model can correct itself
* ``.input`` is not a dict -> error result asking the model to re-issue the call
* the tool raises ``ToolError`` -> error result with content ``"Error: <msg>"``
* the tool raises anything else -> error result containing
  ``"failed unexpectedly"`` (a tool bug must not crash the agent)
* otherwise -> the tool's own ``ToolResult``

Run a tool with ``tool.run(**block.input)``. Build each block the same way as
in Exercise 3.1: ``{"type": "tool_result", "tool_use_id": ..., "content":
...}``, plus ``"is_error": True`` on errors only.
"""

from __future__ import annotations

from typing import Any

from common.harness import SimpleRegistry, ToolError, ToolResult


def dispatch_tools(registry: SimpleRegistry, tool_uses: list[Any]) -> list[dict[str, Any]]:
    # BEGIN SOLUTION
    blocks = []
    for call in tool_uses:
        result = _run_one(registry, call)
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": call.id,
            "content": result.content,
        }
        if result.is_error:
            block["is_error"] = True
        blocks.append(block)
    return blocks


def _run_one(registry: SimpleRegistry, call: Any) -> ToolResult:
    tool = registry.get(call.name)
    if tool is None:
        available = ", ".join(t.name for t in registry)
        return ToolResult(
            f"Unknown tool {call.name!r}. Available tools: {available}.", is_error=True
        )
    if not isinstance(call.input, dict):
        return ToolResult("Tool input was not a JSON object; re-issue the call.", is_error=True)
    try:
        return tool.run(**call.input)
    except ToolError as exc:
        return ToolResult(f"Error: {exc}", is_error=True)
    except Exception as exc:  # noqa: BLE001 - a tool bug must not kill the run
        return ToolResult(f"Error: {call.name} failed unexpectedly: {exc!r}", is_error=True)
    # END SOLUTION
