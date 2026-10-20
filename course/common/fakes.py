"""A fake model, so every exercise runs offline with no API key and no cost.

The real API returns objects with ``.type``, ``.text``, ``.stop_reason`` and so
on. These dataclasses have the same shape, and ``ScriptedBackend`` replays a
fixed list of them -- which also lets the tests reach situations a real model
rarely produces on demand, like a refusal or a tool call cut off mid-way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeText:
    text: str
    type: str = "text"


@dataclass
class FakeThinking:
    thinking: str = ""
    type: str = "thinking"


@dataclass
class FakeToolUse:
    name: str
    input: Any
    id: str = "toolu_1"
    type: str = "tool_use"


@dataclass
class FakeStopDetails:
    category: str | None = None
    type: str = "refusal"


@dataclass
class FakeMessage:
    content: list[Any]
    stop_reason: str = "end_turn"
    stop_details: FakeStopDetails | None = None
    usage: dict[str, int] = field(default_factory=dict)


class ScriptedBackend:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, responses: list[FakeMessage]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def create(self, *, messages, system, tools):
        # Copy the list so later appends don't rewrite what was "sent".
        self.requests.append({"messages": list(messages), "system": system, "tools": tools})
        if not self.responses:
            raise AssertionError(
                "the scripted model ran out of responses -- is your loop stopping?"
            )
        return self.responses.pop(0)


def text_message(text: str, **kwargs: Any) -> FakeMessage:
    return FakeMessage(content=[FakeText(text)], **kwargs)


def tool_message(name: str, tool_input: Any, block_id: str = "toolu_1", **kwargs: Any):
    kwargs.setdefault("stop_reason", "tool_use")
    return FakeMessage(content=[FakeToolUse(name, tool_input, block_id)], **kwargs)
