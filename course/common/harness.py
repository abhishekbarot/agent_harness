"""The small set of types the exercises build on.

These are deliberately minimal. You build the full versions yourself in the
exercises -- this file only exists so that each section can be done on its own.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolError(Exception):
    """A tool failed in a way the model should hear about and recover from."""


class LoopError(Exception):
    """The loop cannot safely continue."""


class RefusalError(Exception):
    """The model declined the request."""

    def __init__(self, message: str, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category


class Risk(str, Enum):
    READ_ONLY = "read_only"
    WRITE = "write"
    DANGEROUS = "dangerous"


@dataclass
class ToolResult:
    """What a tool hands back. ``is_error`` goes to the model; it is not raised."""

    content: str
    is_error: bool = False


@dataclass
class Tool:
    """A tool is a name, a description, a JSON Schema, and a function."""

    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., ToolResult]
    risk: Risk = Risk.READ_ONLY

    def run(self, **kwargs: Any) -> ToolResult:
        return self.fn(**kwargs)

    def to_api_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class SimpleRegistry:
    """A bare-bones registry for Section 4. You build a proper one in 3.3."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def to_api_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_api_schema() for tool in self._tools.values()]
