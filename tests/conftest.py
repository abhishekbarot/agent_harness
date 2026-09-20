"""Test doubles.

The loop talks to a ``ModelBackend`` protocol, never to ``anthropic`` directly,
so the whole harness can be driven by a scripted transcript. No API key, no
network, no cost -- and the awkward paths (refusal, truncation, pause_turn) are
reachable, which they would not be against a live model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_harness.config import Config


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
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class FakeStopDetails:
    category: str | None = None
    type: str = "refusal"
    explanation: str = ""


@dataclass
class FakeMessage:
    content: list[Any]
    stop_reason: str = "end_turn"
    usage: FakeUsage = field(default_factory=FakeUsage)
    stop_details: FakeStopDetails | None = None


class ScriptedBackend:
    """Replays a fixed list of responses, recording what it was sent."""

    def __init__(self, responses: list[FakeMessage]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def create(self, *, messages, system, tools):
        self.requests.append(
            {
                "messages": [dict(m) for m in messages],
                "system": system,
                "tools": tools,
            }
        )
        if not self.responses:
            raise AssertionError("ScriptedBackend ran out of responses")
        return self.responses.pop(0)


def text_message(text: str, **kwargs: Any) -> FakeMessage:
    return FakeMessage(content=[FakeText(text)], **kwargs)


def tool_message(name: str, tool_input: Any, block_id: str = "toolu_1", **kwargs: Any):
    kwargs.setdefault("stop_reason", "tool_use")
    return FakeMessage(content=[FakeToolUse(name, tool_input, block_id)], **kwargs)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hello.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.py").write_text("def f():\n    return 42\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def config(workspace):
    return Config(
        workspace=workspace,
        permission_mode="auto",
        max_turns=6,
        context_strategy="none",
    )
