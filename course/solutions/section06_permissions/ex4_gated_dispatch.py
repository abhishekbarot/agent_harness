"""Exercise 6.4 -- Put the gate in front of the tools.

Lecture: 6.3 "A denial is a tool result, not an error"

This is Exercise 4.3 again, with permissions. ``gated_dispatch`` takes the
``tool_use`` blocks from one turn and returns one ``tool_result`` block per
call, in the same order. Work in **two passes**:

1. **Check every call first**, one at a time, before running any tool. If two
   calls each needed approval, a person should get one question at a time --
   and no tool should run until every answer is in.
   * unknown tool -> error result naming it (don't ask anyone about it)
   * ``policy.check(tool, block.input)`` denies -> error result whose content
     is ``"The user declined this tool call. Reason: <reason>"``
2. **Then run the approved calls**, in order, with ``tool.run(**block.input)``.
   A ``ToolError`` becomes an error result ``"Error: <msg>"``.

A denial does **not** raise or stop the run. It goes back to the model as an
ordinary error result, so the model reads "the user said no" and proposes
something else.

Build each block as before: ``{"type": "tool_result", "tool_use_id": ...,
"content": ...}``, plus ``"is_error": True`` on errors only. You can assume
every ``block.input`` is a dict.
"""

from __future__ import annotations

from typing import Any

from common.harness import SimpleRegistry, ToolError, ToolResult
from ex3_policy import PermissionPolicy


def gated_dispatch(
    registry: SimpleRegistry, policy: PermissionPolicy, tool_uses: list[Any]
) -> list[dict[str, Any]]:
    # BEGIN SOLUTION
    results: dict[str, ToolResult] = {}
    approved = []
    for call in tool_uses:
        tool = registry.get(call.name)
        if tool is None:
            results[call.id] = ToolResult(f"Unknown tool {call.name!r}.", is_error=True)
            continue
        decision = policy.check(tool, call.input)
        if not decision.allowed:
            results[call.id] = ToolResult(
                f"The user declined this tool call. Reason: {decision.reason}", is_error=True
            )
            continue
        approved.append((call, tool))

    for call, tool in approved:
        try:
            results[call.id] = tool.run(**call.input)
        except ToolError as exc:
            results[call.id] = ToolResult(f"Error: {exc}", is_error=True)

    blocks = []
    for call in tool_uses:
        result = results[call.id]
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": call.id,
            "content": result.content,
        }
        if result.is_error:
            block["is_error"] = True
        blocks.append(block)
    return blocks
    # END SOLUTION
