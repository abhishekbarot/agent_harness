"""Exercise 4.4 -- The agent loop.

Lectures: 4.7 "The append-only transcript", 4.8 "Turn ceilings"

Put 4.1-4.3 together. They are imported for you below, so this exercise runs on
your own code -- if a test here fails, make sure 4.1-4.3 pass first.

``run_agent`` sends the conversation to ``backend.create(messages=...,
system=..., tools=...)`` in a loop until the model is done, and returns a
``RunResult``. The rules:

1. Start the history with ``{"role": "user", "content": prompt}``.
2. After every response, append ``{"role": "assistant", "content":
   response.content}`` -- the **whole** content list, not just the text. The
   thinking and tool_use blocks are needed to continue the conversation.
3. The history is **append-only**. Never edit or remove an earlier message.
4. ``next_action`` decides what happens:
   * ``"run_tools"``: send *all* results back in **one** user message
     (``{"role": "user", "content": dispatch_tools(...)}``), then loop.
   * ``"resume"``: loop again without adding anything. Count consecutive
     resumes; when they reach ``max_pause_resumes``, raise ``LoopError``.
     Reset the count once a turn finishes.
   * ``"finish"``: stop with ``stop_reason="end_turn"``.
   * ``"max_tokens"``: stop with ``stop_reason="max_tokens"``.
5. If ``max_turns`` responses go by without finishing, stop with
   ``stop_reason="max_turns"``.
6. ``RunResult.text`` is the text of the most recent *finished* turn. A turn
   that was paused and resumed spans several responses -- join their non-empty
   texts with ``"\\n"``.
7. ``RunResult.turns`` counts the responses received.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.harness import LoopError, SimpleRegistry
from ex1_text_of import text_of
from ex2_next_action import next_action
from ex3_dispatch_tools import dispatch_tools


@dataclass
class RunResult:
    text: str
    stop_reason: str
    messages: list[dict[str, Any]]
    turns: int


def run_agent(
    backend: Any,
    registry: SimpleRegistry,
    prompt: str,
    *,
    system: str = "",
    max_turns: int = 10,
    max_pause_resumes: int = 5,
) -> RunResult:
    raise NotImplementedError("Exercise 4.4: write this part")
