"""Exercise 3.1 -- Turn a tool result into an API content block.

Lecture: 3.3 "tool_use and tool_result blocks, matched by ID"

When the model calls a tool, your harness runs it and sends the outcome back as
a ``tool_result`` content block. The block must name the ``tool_use_id`` it
answers, or the API cannot pair the result with the call.

Write ``to_block`` so that:

* it returns ``{"type": "tool_result", "tool_use_id": ..., "content": ...}``
* it adds ``"is_error": True`` only when the result is an error -- leave the key
  out entirely otherwise, rather than sending ``False``
"""

from __future__ import annotations

from typing import Any

from common.harness import ToolResult


def to_block(result: ToolResult, tool_use_id: str) -> dict[str, Any]:
    """Build the ``tool_result`` block for one tool call."""
    # BEGIN SOLUTION
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": result.content,
    }
    if result.is_error:
        block["is_error"] = True
    return block
    # END SOLUTION
