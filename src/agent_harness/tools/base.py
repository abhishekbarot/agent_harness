"""Tool protocol, results, and registry.

Design note: each capability is a *dedicated* tool rather than a single `bash`
escape hatch. Bash gives the model breadth but hands the harness an opaque
command string -- the same shape for `grep` and for `git push`. A typed tool
gives the harness an action-specific hook it can gate, audit, render, and mark
parallel-safe. `run_command` stays available for breadth, at the highest risk
tier.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Risk(str, Enum):
    """How much damage a tool can do, which drives the permission policy."""

    READ_ONLY = "read_only"  # observes state; safe to auto-approve and parallelize
    WRITE = "write"  # mutates the workspace; reversible via version control
    DANGEROUS = "dangerous"  # arbitrary execution or hard-to-reverse effects


@dataclass
class ToolResult:
    """What a tool hands back to the loop.

    ``is_error`` is surfaced to the model rather than raised, so it can read the
    message and try something else. A failed tool still produces a result --
    dropping one desynchronizes the transcript and the API rejects the next turn.
    """

    content: str
    is_error: bool = False
    # Not sent to the model; for logs, evals, and tests.
    metadata: dict[str, Any] | None = None

    def to_block(self, tool_use_id: str) -> dict[str, Any]:
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": self.content,
        }
        if self.is_error:
            block["is_error"] = True
        return block


class Tool(ABC):
    """A capability the model can invoke.

    Subclasses declare a name, description, JSON Schema, and risk tier, then
    implement ``run``. Validation is declared in the schema *and* re-checked in
    ``run`` -- tool input is model output, and never trusted on its own.
    """

    name: str
    description: str
    risk: Risk = Risk.READ_ONLY
    # Read-only tools can be dispatched concurrently within one assistant turn.
    parallel_safe: bool = True

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for this tool's arguments."""

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool. Raise ``ToolError`` for recoverable failures."""

    def to_api_schema(self) -> dict[str, Any]:
        """The tool definition sent to the Messages API.

        ``strict`` plus ``additionalProperties: false`` makes the API guarantee
        that ``tool_use.input`` validates against the schema.

        Strict mode wants every declared property listed in ``required``. An
        optional argument is therefore expressed as required-but-nullable
        (``{"type": ["string", "null"]}``), not by omission from ``required``.
        ``validate_schema`` enforces that here, so a mistake surfaces when the
        tool is registered instead of as a 400 on the first live request.
        """
        schema = dict(self.input_schema)
        schema.setdefault("additionalProperties", False)
        self.validate_schema(schema)
        return {
            "name": self.name,
            "description": self.description,
            "strict": True,
            "input_schema": schema,
        }

    def validate_schema(self, schema: dict[str, Any]) -> None:
        """Check the schema satisfies what strict tool use requires."""
        properties = set(schema.get("properties", {}))
        required = set(schema.get("required", []))
        missing = properties - required
        if missing:
            raise ValueError(
                f"tool {self.name!r} declares {sorted(missing)} outside 'required'; "
                "strict tool use needs every property required -- make optional "
                'arguments nullable instead, e.g. {"type": ["string", "null"]}'
            )
        if schema.get("additionalProperties") is not False:
            raise ValueError(
                f"tool {self.name!r} must set additionalProperties to false"
            )

    def describe(self) -> str:
        return f"{self.name} ({self.risk.value})"


class ToolRegistry:
    """The set of tools available to a run.

    Order is fixed at registration and never changes mid-run: the tool list is
    the first thing rendered into the cached request prefix, so reordering or
    swapping tools invalidates the entire prompt cache.
    """

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    def to_api_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_api_schema() for tool in self._tools.values()]

    def fingerprint(self) -> str:
        """Stable hash input for the tool set.

        Log this at the start of a run: if it changes between runs that should
        share a cache, that alone explains a zero cache-hit rate.
        """
        return json.dumps(self.to_api_schemas(), sort_keys=True)
