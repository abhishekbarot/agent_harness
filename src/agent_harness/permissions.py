"""The permission gate.

The model proposes a tool call; the policy decides whether it runs. This is the
layer that makes an agent safe to point at a real workspace, and it is the
reason the tool surface is typed: a `write_file` call carries a path the policy
can inspect, where `bash -c "..."` carries only an opaque string.

A denial is not an error. It becomes a normal ``tool_result`` marked
``is_error``, so the model sees "the user declined this" and can propose
something else instead of the run aborting.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Protocol

from .logging_setup import get_logger
from .tools.base import Risk, Tool

log = get_logger("permissions")


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    # Remember this answer for the rest of the run.
    remember: bool = False

    @classmethod
    def allow(cls, reason: str = "", remember: bool = False) -> Decision:
        return cls(True, reason, remember)

    @classmethod
    def deny(cls, reason: str, remember: bool = False) -> Decision:
        return cls(False, reason, remember)


class Approver(Protocol):
    """Asked to adjudicate any call the policy will not decide on its own."""

    def __call__(self, tool: Tool, tool_input: dict[str, Any]) -> Decision: ...


def auto_approve(tool: Tool, tool_input: dict[str, Any]) -> Decision:
    """Approve everything. For evals, CI, and other unattended runs."""
    return Decision.allow("auto-approved")


def always_deny(tool: Tool, tool_input: dict[str, Any]) -> Decision:
    return Decision.deny("all tool calls are denied in this mode")


class ConsoleApprover:
    """Prompt a human on stdin.

    Falls back to denying when there is no TTY -- an unattended run must never
    block forever on a prompt nobody will answer.
    """

    def __init__(self, stream: Any = None) -> None:
        self.stream = stream or sys.stdin

    def __call__(self, tool: Tool, tool_input: dict[str, Any]) -> Decision:
        if not hasattr(self.stream, "isatty") or not self.stream.isatty():
            return Decision.deny(
                "no interactive terminal available to approve this call; "
                "re-run with permission_mode='auto' to allow it"
            )

        print(f"\n  Tool call: {tool.name}  [{tool.risk.value}]", file=sys.stderr)
        for key, value in tool_input.items():
            rendered = str(value)
            if len(rendered) > 500:
                rendered = f"{rendered[:500]}... [{len(rendered)} chars total]"
            print(f"    {key}: {rendered}", file=sys.stderr)
        print("  Allow? [y]es / [n]o / [a]lways / [never]: ", end="", file=sys.stderr, flush=True)

        answer = self.stream.readline().strip().lower()
        if answer in ("a", "always"):
            return Decision.allow("approved for the rest of the run", remember=True)
        if answer in ("y", "yes"):
            return Decision.allow("approved by user")
        if answer == "never":
            return Decision.deny("denied for the rest of the run", remember=True)
        return Decision.deny("denied by user")


class PermissionPolicy:
    """Maps (mode, tool risk) to allow / ask / deny.

    Modes:
      ``auto``      run everything without asking (unattended runs, evals)
      ``ask``       read-only runs freely; writes and shell go to the approver
      ``readonly``  read-only runs freely; everything else is denied outright
      ``deny``      nothing runs
    """

    def __init__(self, mode: str = "ask", approver: Approver | None = None) -> None:
        self.mode = mode
        self.approver = approver or ConsoleApprover()
        # Session-scoped overrides from an "always"/"never" answer.
        self._remembered: dict[str, Decision] = {}

    def check(self, tool: Tool, tool_input: dict[str, Any]) -> Decision:
        if self.mode == "deny":
            return Decision.deny("permission mode is 'deny'")

        remembered = self._remembered.get(tool.name)
        if remembered is not None:
            return remembered

        if self.mode == "auto":
            return Decision.allow("permission mode is 'auto'")

        if tool.risk is Risk.READ_ONLY:
            return Decision.allow("read-only tool")

        if self.mode == "readonly":
            return Decision.deny(
                f"{tool.name} is a {tool.risk.value} tool and the harness is in "
                "read-only mode"
            )

        decision = self.approver(tool, tool_input)
        if decision.remember:
            self._remembered[tool.name] = Decision(decision.allowed, decision.reason)
        log.debug(
            "permission decision",
            extra={"tool": tool.name, "allowed": decision.allowed, "reason": decision.reason},
        )
        return decision


def build_policy(mode: str, approver: Approver | None = None) -> PermissionPolicy:
    """Construct the policy for a mode, picking a sensible default approver."""
    if approver is None:
        if mode == "auto":
            approver = auto_approve
        elif mode in ("deny", "readonly"):
            approver = always_deny
        else:
            approver = ConsoleApprover()
    return PermissionPolicy(mode=mode, approver=approver)
