#!/usr/bin/env python3
"""Run the harness end to end with no API key and no network.

The loop talks to a ``ModelBackend`` protocol, so a scripted backend can stand
in for the model. That is what the test suite uses, and it is the fastest way to
see the moving parts: tool dispatch, the permission gate, result batching, the
append-only transcript, and usage accounting.

    python examples/offline_demo.py
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_harness import Agent, Config, Decision, PermissionPolicy  # noqa: E402
from agent_harness.logging_setup import configure  # noqa: E402

# -- a scripted stand-in for the model ------------------------------------


@dataclass
class Text:
    text: str
    type: str = "text"


@dataclass
class ToolUse:
    name: str
    input: dict
    id: str
    type: str = "tool_use"


@dataclass
class Usage:
    input_tokens: int = 1200
    output_tokens: int = 180
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 900


@dataclass
class Message:
    content: list
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)
    stop_details: Any = None


class ScriptedBackend:
    def __init__(self, responses):
        self.responses = list(responses)

    def create(self, *, messages, system, tools):
        return self.responses.pop(0)


SCRIPT = [
    # Turn 1: two read-only calls at once -- the harness runs these in parallel
    # and returns both results in a single user message.
    Message(
        content=[
            Text("Let me look around first."),
            ToolUse("list_dir", {"path": "."}, "toolu_1"),
            ToolUse("read_file", {"path": "notes.txt"}, "toolu_2"),
        ],
        stop_reason="tool_use",
    ),
    # Turn 2: a write. This one has to pass the permission gate.
    Message(
        content=[
            Text("I'll record the third fruit."),
            ToolUse("write_file", {"path": "answer.txt", "content": "cherry\n"}, "toolu_3"),
        ],
        stop_reason="tool_use",
    ),
    # Turn 3: a shell command, which the demo approver refuses.
    Message(
        content=[ToolUse("run_command", {"command": "rm -rf ."}, "toolu_4")],
        stop_reason="tool_use",
    ),
    # Turn 4: the model reacts to the refusal and finishes.
    Message(content=[Text("The third fruit is cherry. I left the directory alone.")]),
]


def demo_approver(tool, tool_input):
    """Approve writes, refuse shell commands -- a stand-in for a human at a TTY."""
    if tool.name == "run_command":
        return Decision.deny("the demo policy never runs shell commands")
    return Decision.allow("demo policy allows writes")


def main() -> int:
    configure(level="INFO", fmt="text")
    workspace = Path(tempfile.mkdtemp(prefix="harness-demo-"))
    (workspace / "notes.txt").write_text("apple\nbanana\ncherry\n", encoding="utf-8")

    agent = Agent(
        Config(workspace=workspace, permission_mode="ask", context_strategy="none"),
        backend=ScriptedBackend(SCRIPT),
        policy=PermissionPolicy("ask", demo_approver),
    )
    result = agent.run("Which fruit is third in notes.txt? Write it to answer.txt.")

    print("\n" + "=" * 62)
    print("final answer:", result.text)
    print("=" * 62)

    print("\ntool calls:")
    for call in result.tool_calls:
        status = "ok" if call.allowed and not call.is_error else (
            "denied" if not call.allowed else "error"
        )
        print(f"  {call.name:<13} {status:<7} {call.result_preview.splitlines()[:1]}")

    print("\ntranscript (append-only):")
    for i, message in enumerate(result.messages):
        kinds = (
            [b.get("type") for b in message["content"]]
            if isinstance(message["content"], list)
            and message["content"]
            and isinstance(message["content"][0], dict)
            else [getattr(b, "type", "text") for b in message["content"]]
            if isinstance(message["content"], list)
            else ["text"]
        )
        print(f"  {i}: {message['role']:<9} {kinds}")

    print("\nusage:")
    for key, value in result.summary(agent.config.model).items():
        print(f"  {key}: {value}")

    print(f"\nwrote: {workspace / 'answer.txt'} -> "
          f"{(workspace / 'answer.txt').read_text().strip()!r}")
    print(f"workspace intact: {sorted(p.name for p in workspace.iterdir())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
