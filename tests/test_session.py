from __future__ import annotations

import json

from agent_harness.loop import Agent
from agent_harness.session import save_transcript, to_jsonable
from conftest import ScriptedBackend, text_message, tool_message


class Block:
    """Stands in for an SDK content block, which is a Pydantic model."""

    def __init__(self, text):
        self.text = text
        self.type = "text"

    def to_dict(self):
        return {"type": self.type, "text": self.text}


def test_sdk_blocks_are_converted():
    assert to_jsonable(Block("hi")) == {"type": "text", "text": "hi"}
    assert to_jsonable([Block("a"), {"k": Block("b")}]) == [
        {"type": "text", "text": "a"},
        {"k": {"type": "text", "text": "b"}},
    ]


def test_primitives_pass_through():
    assert to_jsonable({"a": [1, 2.5, True, None, "s"]}) == {"a": [1, 2.5, True, None, "s"]}


def test_transcript_round_trips(config, tmp_path):
    agent = Agent(
        config,
        backend=ScriptedBackend(
            [tool_message("read_file", {"path": "hello.txt"}), text_message("done")]
        ),
    )
    result = agent.run("read the file")

    path = save_transcript(result, tmp_path / "runs", config.model, "read the file")
    payload = json.loads(path.read_text())

    assert payload["prompt"] == "read the file"
    assert payload["final_text"] == "done"
    assert payload["summary"]["completed"] is True
    assert len(payload["tool_calls"]) == 1
    assert payload["tool_calls"][0]["name"] == "read_file"
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant", "user", "assistant"]
