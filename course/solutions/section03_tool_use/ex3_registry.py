"""Exercise 3.3 -- A tool registry.

Lecture: 3.6 "A tool registry: why order and stability matter"

The registry holds the tools available to a run. It looks like a plain dict,
but two rules make it worth its own class:

* **Names are unique.** Registering a second tool with an existing name raises
  ``ValueError`` -- the model calls tools by name, so a duplicate is ambiguous.
* **Order never changes.** The tool list is sent at the very start of every
  request, so it is part of the prompt-cache prefix. ``names()`` and
  ``to_api_schemas()`` must return tools in the order they were registered.

``get`` returns ``None`` for an unknown name instead of raising -- an unknown
tool is something the model gets told about, not a crash.
"""

from __future__ import annotations

from typing import Any

from common.harness import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        # BEGIN SOLUTION
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)
        # END SOLUTION

    def register(self, tool: Tool) -> None:
        # BEGIN SOLUTION
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool
        # END SOLUTION

    def get(self, name: str) -> Tool | None:
        # BEGIN SOLUTION
        return self._tools.get(name)
        # END SOLUTION

    def names(self) -> list[str]:
        # BEGIN SOLUTION
        return list(self._tools)
        # END SOLUTION

    def __len__(self) -> int:
        # BEGIN SOLUTION
        return len(self._tools)
        # END SOLUTION

    def __contains__(self, name: object) -> bool:
        # BEGIN SOLUTION
        return name in self._tools
        # END SOLUTION

    def to_api_schemas(self) -> list[dict[str, Any]]:
        # BEGIN SOLUTION
        return [tool.to_api_schema() for tool in self._tools.values()]
        # END SOLUTION
