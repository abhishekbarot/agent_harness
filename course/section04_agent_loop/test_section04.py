"""Section 4 -- The agent loop. Run with: pytest course/section04_agent_loop"""

from __future__ import annotations

from itertools import pairwise

import pytest

from common.fakes import (
    FakeMessage,
    FakeStopDetails,
    FakeText,
    FakeThinking,
    FakeToolUse,
    ScriptedBackend,
    text_message,
    tool_message,
)
from common.harness import LoopError, RefusalError, SimpleRegistry, Tool, ToolError, ToolResult
from loader import load


def make_tool(name: str, fn) -> Tool:
    return Tool(name=name, description=name, input_schema={"type": "object"}, fn=fn)


def registry() -> SimpleRegistry:
    def read_file(path: str) -> ToolResult:
        if path == "missing.txt":
            raise ToolError("file not found: missing.txt")
        return ToolResult(f"contents of {path}")

    def crash(**_):
        raise RuntimeError("bug in the tool")

    return SimpleRegistry([make_tool("read_file", read_file), make_tool("crash", crash)])


# -- 4.1 ---------------------------------------------------------------------


class TestEx1TextOf:
    ex = load(__file__, "ex1_text_of")

    def test_joins_text_blocks_and_skips_the_rest(self):
        response = FakeMessage(
            content=[
                FakeThinking("let me think"),
                FakeText("The answer "),
                FakeToolUse("read_file", {"path": "a"}),
                FakeText("is 42."),
            ]
        )
        assert self.ex.text_of(response) == "The answer is 42."

    def test_strips_whitespace(self):
        assert self.ex.text_of(text_message("  done \n")) == "done"

    def test_no_text_is_empty_string(self):
        assert self.ex.text_of(tool_message("read_file", {"path": "a"})) == ""


# -- 4.2 ---------------------------------------------------------------------


class TestEx2NextAction:
    ex = load(__file__, "ex2_next_action")

    def test_end_turn_finishes(self):
        assert self.ex.next_action(text_message("done")) == "finish"

    def test_tool_use_runs_tools(self):
        assert self.ex.next_action(tool_message("read_file", {"path": "a"})) == "run_tools"

    def test_pause_turn_resumes(self):
        assert self.ex.next_action(text_message("...", stop_reason="pause_turn")) == "resume"

    def test_max_tokens_without_a_tool_call_stops(self):
        assert self.ex.next_action(text_message("cut of", stop_reason="max_tokens")) == "max_tokens"

    def test_truncated_tool_call_must_not_run(self):
        truncated = tool_message("write_file", {"path": "a.txt"}, stop_reason="max_tokens")
        with pytest.raises(LoopError):
            self.ex.next_action(truncated)

    def test_refusal_raises_with_its_category(self):
        refused = FakeMessage(
            content=[], stop_reason="refusal", stop_details=FakeStopDetails("cyber")
        )
        with pytest.raises(RefusalError) as info:
            self.ex.next_action(refused)
        assert info.value.category == "cyber"

    def test_refusal_without_details(self):
        with pytest.raises(RefusalError) as info:
            self.ex.next_action(FakeMessage(content=[], stop_reason="refusal"))
        assert info.value.category is None

    def test_unrecognized_stop_without_tools_finishes(self):
        assert self.ex.next_action(text_message("x", stop_reason="stop_sequence")) == "finish"


# -- 4.3 ---------------------------------------------------------------------


class TestEx3DispatchTools:
    ex = load(__file__, "ex3_dispatch_tools")

    def test_runs_a_tool(self):
        [block] = self.ex.dispatch_tools(
            registry(), [FakeToolUse("read_file", {"path": "a.txt"}, "toolu_a")]
        )
        assert block == {
            "type": "tool_result",
            "tool_use_id": "toolu_a",
            "content": "contents of a.txt",
        }

    def test_unknown_tool_lists_the_real_ones(self):
        [block] = self.ex.dispatch_tools(registry(), [FakeToolUse("delete_everything", {})])
        assert block["is_error"] is True
        assert "delete_everything" in block["content"]
        assert "read_file" in block["content"] and "crash" in block["content"]

    def test_non_dict_input_is_an_error_result(self):
        [block] = self.ex.dispatch_tools(registry(), [FakeToolUse("read_file", "a.txt")])
        assert block["is_error"] is True

    def test_tool_error_reaches_the_model(self):
        [block] = self.ex.dispatch_tools(
            registry(), [FakeToolUse("read_file", {"path": "missing.txt"})]
        )
        assert block["is_error"] is True
        assert block["content"].startswith("Error:")
        assert "file not found" in block["content"]

    def test_a_crashing_tool_does_not_crash_the_agent(self):
        [block] = self.ex.dispatch_tools(registry(), [FakeToolUse("crash", {})])
        assert block["is_error"] is True
        assert "failed unexpectedly" in block["content"]

    def test_one_result_per_call_in_order(self):
        calls = [
            FakeToolUse("read_file", {"path": "a"}, "toolu_1"),
            FakeToolUse("nope", {}, "toolu_2"),
            FakeToolUse("crash", {}, "toolu_3"),
        ]
        blocks = self.ex.dispatch_tools(registry(), calls)
        assert [b["tool_use_id"] for b in blocks] == ["toolu_1", "toolu_2", "toolu_3"]
        assert "is_error" not in blocks[0]


# -- 4.4 ---------------------------------------------------------------------


class TestEx4RunAgent:
    ex = load(__file__, "ex4_run_agent")

    def run(self, responses, **kwargs):
        backend = ScriptedBackend(responses)
        result = self.ex.run_agent(backend, registry(), "do the task", **kwargs)
        return result, backend

    def test_answers_without_tools(self):
        result, _ = self.run([text_message("hello")])
        assert result.text == "hello"
        assert result.stop_reason == "end_turn"
        assert result.turns == 1

    def test_tool_round_trip(self):
        result, backend = self.run(
            [tool_message("read_file", {"path": "a.txt"}), text_message("it says hi")]
        )
        assert [m["role"] for m in result.messages] == ["user", "assistant", "user", "assistant"]
        tool_result = result.messages[2]["content"][0]
        assert tool_result["type"] == "tool_result"
        assert tool_result["content"] == "contents of a.txt"
        assert result.text == "it says hi"
        assert len(backend.requests) == 2

    def test_assistant_content_is_stored_whole(self):
        content = [FakeThinking("plan"), FakeToolUse("read_file", {"path": "a"})]
        result, _ = self.run([FakeMessage(content, stop_reason="tool_use"), text_message("ok")])
        assert result.messages[1]["content"] is content, "store response.content, not just text"

    def test_parallel_results_come_back_in_one_message(self):
        two = FakeMessage(
            [
                FakeToolUse("read_file", {"path": "a"}, "t1"),
                FakeToolUse("read_file", {"path": "b"}, "t2"),
            ],
            stop_reason="tool_use",
        )
        result, _ = self.run([two, text_message("done")])
        user_turns = [m for m in result.messages if m["role"] == "user"]
        assert len(user_turns) == 2, "the prompt, then ONE message with both results"
        assert len(user_turns[1]["content"]) == 2

    def test_history_is_append_only(self):
        """Every request's history must be a prefix of the next one."""
        _, backend = self.run(
            [
                tool_message("read_file", {"path": "a"}),
                tool_message("read_file", {"path": "b"}),
                text_message("done"),
            ]
        )
        sent = [r["messages"] for r in backend.requests]
        for earlier, later in pairwise(sent):
            assert later[: len(earlier)] == earlier

    def test_system_and_tools_are_sent(self):
        _, backend = self.run([text_message("ok")], system="Be brief.")
        assert backend.requests[0]["system"] == "Be brief."
        assert [t["name"] for t in backend.requests[0]["tools"]] == ["read_file", "crash"]

    def test_tool_errors_do_not_stop_the_run(self):
        result, _ = self.run(
            [tool_message("read_file", {"path": "missing.txt"}), text_message("recovered")]
        )
        assert result.stop_reason == "end_turn"
        assert result.messages[2]["content"][0]["is_error"] is True

    def test_turn_ceiling(self):
        looping = [tool_message("read_file", {"path": "a"}, block_id=f"t{i}") for i in range(3)]
        result, _ = self.run(looping, max_turns=3)
        assert result.stop_reason == "max_turns"
        assert result.turns == 3

    def test_max_tokens_stops(self):
        result, _ = self.run([text_message("partial answ", stop_reason="max_tokens")])
        assert result.stop_reason == "max_tokens"
        assert result.text == "partial answ"

    def test_truncated_tool_call_raises(self):
        with pytest.raises(LoopError):
            self.run([tool_message("read_file", {"path": "a"}, stop_reason="max_tokens")])

    def test_pause_then_resume_joins_text(self):
        result, backend = self.run(
            [
                text_message("searching...", stop_reason="pause_turn"),
                text_message("found it"),
            ]
        )
        assert result.text == "searching...\nfound it"
        assert result.stop_reason == "end_turn"
        # Resuming sends the conversation back with nothing new added.
        assert backend.requests[1]["messages"][-1]["role"] == "assistant"

    def test_endless_pausing_is_bounded(self):
        pauses = [text_message("...", stop_reason="pause_turn") for _ in range(5)]
        with pytest.raises(LoopError):
            self.run(pauses, max_pause_resumes=3)

    def test_pause_count_resets_after_a_finished_turn(self):
        responses = [
            text_message("...", stop_reason="pause_turn"),
            text_message("...", stop_reason="pause_turn"),
            tool_message("read_file", {"path": "a"}),
            text_message("...", stop_reason="pause_turn"),
            text_message("...", stop_reason="pause_turn"),
            text_message("done"),
        ]
        result, _ = self.run(responses, max_pause_resumes=3)
        assert result.stop_reason == "end_turn"
