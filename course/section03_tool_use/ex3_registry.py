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
        raise NotImplementedError("Exercise 3.3: write this part")

    def register(self, tool: Tool) -> None:
        raise NotImplementedError("Exercise 3.3: write this part")

    def get(self, name: str) -> Tool | None:
        raise NotImplementedError("Exercise 3.3: write this part")

    def names(self) -> list[str]:
        raise NotImplementedError("Exercise 3.3: write this part")

    def __len__(self) -> int:
        raise NotImplementedError("Exercise 3.3: write this part")

    def __contains__(self, name: object) -> bool:
        raise NotImplementedError("Exercise 3.3: write this part")

    def to_api_schemas(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Exercise 3.3: write this part")
