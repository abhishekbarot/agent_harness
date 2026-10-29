"""Exercise 4.2 -- Decide what the loop does next.

Lecture: 4.2-4.6 (the stop_reason lectures)

``stop_reason`` tells you why the model stopped. Map it to the loop's next
move. Return one of these strings:

==================  ==========================================================
``"finish"``        ``end_turn`` -- or any other stop with no ``tool_use``
                    blocks in the content. The model is done.
``"run_tools"``     ``tool_use`` -- run the tools, send results, loop again.
``"resume"``        ``pause_turn`` -- a server-side tool paused the turn; send
                    the conversation back as-is to let it continue.
``"max_tokens"``    ``max_tokens`` with **no** ``tool_use`` block -- the answer
                    was cut off; stop and report it.
==================  ==========================================================

Two cases must raise instead:

* ``refusal`` -> raise ``RefusalError`` with the category from
  ``response.stop_details.category`` (``stop_details`` may be ``None``).
* ``max_tokens`` **with** a ``tool_use`` block -> raise ``LoopError``. A
  tool call cut off mid-way still looks like a valid object, but its arguments
  are incomplete. Running it acts on a call the model never finished writing.
"""

from __future__ import annotations

from typing import Any

from common.harness import LoopError, RefusalError


def next_action(response: Any) -> str:
    # BEGIN SOLUTION
    reason = response.stop_reason
    has_tool_use = any(getattr(b, "type", None) == "tool_use" for b in response.content)

    if reason == "refusal":
        details = response.stop_details
        category = details.category if details is not None else None
        raise RefusalError(f"the model declined this request (category: {category})", category)
    if reason == "pause_turn":
        return "resume"
    if reason == "max_tokens":
        if has_tool_use:
            raise LoopError("the response was cut off in the middle of a tool call")
        return "max_tokens"
    if reason == "tool_use" and has_tool_use:
        return "run_tools"
    return "finish"
    # END SOLUTION
