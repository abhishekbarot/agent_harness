"""Exercise 6.2 -- Ask a human.

Lecture: 6.4 "Interactive approval, always and never, no-terminal deny"

In ``ask`` mode, risky calls go to an approver. Write ``ConsoleApprover``, which
shows the call to a person and reads their answer. Calling it returns a
``Decision``.

``ConsoleApprover(stream, out)`` reads answers from ``stream`` (normally
``sys.stdin``) and writes the prompt to ``out`` (normally ``sys.stderr``, so
the agent's real output on stdout stays clean).

1. **No terminal, no question.** If ``stream`` has no ``isatty`` method, or
   ``stream.isatty()`` is false, return ``Decision.deny`` with a reason that
   mentions ``"no interactive terminal"`` -- without printing or reading
   anything. An unattended run must never hang on a prompt nobody will answer.
2. Otherwise print, to ``out``:
   * the tool name and the call's risk, ``tool.risk_for(tool_input).value``
   * one line per argument, ``key: value``. If ``str(value)`` is longer than
     500 characters, show the first 500 followed by
     ``"... [N chars total]"`` -- a 50 KB file write should not flood the screen
   * ``"Allow? [y]es / [n]o / [a]lways / [never]: "``
3. Read one line, strip it and lowercase it, then:

   ===================  =================================================
   ``y`` / ``yes``      ``Decision.allow(...)``
   ``a`` / ``always``   ``Decision.allow(..., remember=True)``
   ``never``            ``Decision.deny(..., remember=True)``
   anything else        ``Decision.deny(...)`` -- when unsure, don't run it
   ===================  =================================================
"""

from __future__ import annotations

import sys
from typing import Any

from common.harness import Decision, Tool

MAX_SHOWN_CHARS = 500


class ConsoleApprover:
    def __init__(self, stream: Any = None, out: Any = None) -> None:
        self.stream = stream if stream is not None else sys.stdin
        self.out = out if out is not None else sys.stderr

    def __call__(self, tool: Tool, tool_input: dict[str, Any]) -> Decision:
        raise NotImplementedError("Exercise 6.2: write this part")
