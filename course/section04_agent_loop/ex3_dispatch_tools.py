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
    raise NotImplementedError("Exercise 4.3: write this part")
