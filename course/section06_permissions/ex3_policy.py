"""Exercise 6.3 -- The permission policy.

Lectures: 6.2 "Permission modes", 6.4 (remembered answers), 6.5 "Per-call risk"

The policy is the gate every tool call passes through. ``check(tool,
tool_input)`` returns a ``Decision``. ``decide`` from Exercise 6.1 is imported
for you. Apply these rules **in this order**:

1. Mode ``deny`` denies everything -- even a call the user said "always" to.
2. If the user already answered "always" or "never" for this tool (by name),
   return that remembered decision without asking again.
3. Rate **this call**: ``tool.risk_for(tool_input)``, not ``tool.risk``. One
   tool can span tiers -- reading memory is harmless, deleting it is not.
4. ``decide(mode, risk)``:
   * ``"allow"`` -> ``Decision.allow(...)``
   * ``"deny"``  -> ``Decision.deny(...)`` with a reason naming the tool and the
     risk, e.g. ``"write_file is a write call and the harness is read-only"``
   * ``"ask"``   -> ask ``self.approver(tool, tool_input)``. If its decision has
     ``remember=True``, store it for this tool name. Return it.

An approver is anything callable as ``approver(tool, tool_input) -> Decision``,
like your ``ConsoleApprover`` from 6.2, or a plain function in tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from common.harness import Decision, Tool
from ex1_decide import decide

Approver = Callable[[Tool, dict[str, Any]], Decision]


class PermissionPolicy:
    def __init__(self, mode: str, approver: Approver) -> None:
        self.mode = mode
        self.approver = approver
        self.remembered: dict[str, Decision] = {}

    def check(self, tool: Tool, tool_input: dict[str, Any]) -> Decision:
        raise NotImplementedError("Exercise 6.3: write this part")
