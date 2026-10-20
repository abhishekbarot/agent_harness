"""Exercise 3.4 -- Send every tool result back in one message.

Lecture: 3.4 "Parallel tool calls: all results go back in one message"

One assistant turn can contain several ``tool_use`` blocks. After running them,
your harness replies with a single ``user`` message holding all the
``tool_result`` blocks. Two rules:

* **One message, original order.** Results go in one ``user`` message, in the
  same order as the calls. Splitting them across several messages teaches the
  model to stop making parallel calls.
* **Every call gets exactly one result.** If a call has no entry in
  ``results`` (it was skipped, or crashed before producing anything), send an
  error result for it anyway, mentioning that no result was produced. A
  missing ``tool_result`` makes the API reject the next request.

``to_block`` from Exercise 3.1 is already imported for you -- reuse it.
"""

from __future__ import annotations

from typing import Any

from common.harness import ToolResult
from ex1_tool_result import to_block


def batch_results(tool_uses: list[Any], results: dict[str, ToolResult]) -> dict[str, Any]:
    """Build the user message answering every ``tool_use`` block.

    ``tool_uses`` are content blocks with ``.id`` and ``.name``; ``results``
    maps a tool_use id to its result.
    """
    raise NotImplementedError("Exercise 3.4: write this part")
