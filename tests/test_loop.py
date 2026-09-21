"""Loop behaviour.

These are the decisions that make a harness a harness: what each stop_reason
means, what happens to a refused call, how results are batched, and when to
stop.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from agent_harness.config import Config
from agent_harness.errors import BudgetExceededError, LoopError, RefusalError
from agent_harness.loop import Agent
from agent_harness.permissions import Decision, PermissionPolicy, build_policy
from agent_harness.tools.base import Risk, Tool
from conftest import (
    FakeMessage,
    FakeStopDetails,
    FakeText,
    FakeThinking,
    FakeToolUse,
    FakeUsage,
    ScriptedBackend,
    text_message,
    tool_message,
)


def make_agent(config, responses, **kwargs):
    return Agent(config, backend=ScriptedBackend(responses), **kwargs)


class TestBasicFlow:
    def test_plain_answer_completes(self, config):
        agent = make_agent(config, [text_message("Paris.")])
        result = agent.run("What is the capital of France?")

        assert result.completed
        assert result.text == "Paris."
        assert result.tool_calls == []
        assert result.usage.turns == 1

    def test_tool_call_then_answer(self, config):
        agent = make_agent(
            config,
            [
                tool_message("read_file", {"path": "hello.txt"}),
                text_message("The file starts with alpha."),
            ],
        )
        result = agent.run("Read hello.txt")

        assert result.completed
        assert [c.name for c in result.tool_calls] == ["read_file"]
        assert result.tool_calls[0].allowed
        assert not result.tool_calls[0].is_error

    def test_transcript_shape(self, config):
        agent = make_agent(
            config,
            [tool_message("read_file", {"path": "hello.txt"}), text_message("done")],
        )
        result = agent.run("read it")

        roles = [m["role"] for m in result.messages]
        assert roles == ["user", "assistant", "user", "assistant"]
        # The tool result rides in a user message, as content blocks.
        assert result.messages[2]["content"][0]["type"] == "tool_result"

    def test_assistant_turn_is_stored_verbatim(self, config):
        """Thinking and tool_use blocks must survive into the next request.

        Keeping only the text would drop the blocks the API needs to continue.
        """
        blocks = [FakeThinking("reasoning"), FakeToolUse("read_file", {"path": "hello.txt"})]
        agent = make_agent(
            config,
            [FakeMessage(content=blocks, stop_reason="tool_use"), text_message("ok")],
        )
        result = agent.run("go")

        assert result.messages[1]["content"] is blocks


class TestToolResultBatching:
    def test_parallel_calls_return_in_one_user_message(self, config):
        two_calls = FakeMessage(
            content=[
                FakeToolUse("read_file", {"path": "hello.txt"}, "toolu_a"),
                FakeToolUse("list_dir", {"path": "."}, "toolu_b"),
            ],
            stop_reason="tool_use",
        )
        agent = make_agent(config, [two_calls, text_message("both read")])
        result = agent.run("read and list")

        tool_turns = [m for m in result.messages if m["role"] == "user"][1:]
        assert len(tool_turns) == 1, "results must not be split across messages"
        assert len(tool_turns[0]["content"]) == 2

    def test_every_tool_use_id_gets_exactly_one_result(self, config):
        """A missing tool_result desynchronizes the transcript and the API 400s."""
        calls = FakeMessage(
            content=[
                FakeToolUse("read_file", {"path": "hello.txt"}, "toolu_a"),
                FakeToolUse("nonexistent_tool", {}, "toolu_b"),
                FakeToolUse("read_file", {"path": "missing.txt"}, "toolu_c"),
            ],
            stop_reason="tool_use",
        )
        agent = make_agent(config, [calls, text_message("done")])
        result = agent.run("go")

        results = [m for m in result.messages if m["role"] == "user"][1]["content"]
        assert [b["tool_use_id"] for b in results] == ["toolu_a", "toolu_b", "toolu_c"]

    def test_results_keep_the_models_original_order(self, config):
        calls = FakeMessage(
            content=[
                FakeToolUse("list_dir", {"path": "."}, "toolu_1"),
                FakeToolUse("read_file", {"path": "hello.txt"}, "toolu_2"),
                FakeToolUse("search_files", {"pattern": "alpha"}, "toolu_3"),
            ],
            stop_reason="tool_use",
        )
        agent = make_agent(config, [calls, text_message("done")])
        result = agent.run("go")

        results = [m for m in result.messages if m["role"] == "user"][1]["content"]
        assert [b["tool_use_id"] for b in results] == ["toolu_1", "toolu_2", "toolu_3"]


class TestFailureHandling:
    def test_failing_tool_produces_an_error_result_not_an_abort(self, config):
        agent = make_agent(
            config,
            [
                tool_message("read_file", {"path": "does-not-exist.txt"}),
                text_message("That file is missing."),
            ],
        )
        result = agent.run("read it")

        assert result.completed  # the run carried on
        assert result.tool_calls[0].is_error
        block = [m for m in result.messages if m["role"] == "user"][1]["content"][0]
        assert block["is_error"] is True
        assert "file not found" in block["content"]

    def test_unknown_tool_is_reported_to_the_model(self, config):
        agent = make_agent(
            config, [tool_message("teleport", {}), text_message("no such tool")]
        )
        result = agent.run("go")

        block = [m for m in result.messages if m["role"] == "user"][1]["content"][0]
        assert block["is_error"] is True
        assert "Unknown tool" in block["content"]
        assert "read_file" in block["content"]  # tells the model what does exist

    def test_non_object_tool_input_is_rejected(self, config):
        agent = make_agent(
            config, [tool_message("read_file", "not-a-dict"), text_message("ok")]
        )
        result = agent.run("go")

        block = [m for m in result.messages if m["role"] == "user"][1]["content"][0]
        assert block["is_error"] is True
        assert "not a JSON object" in block["content"]

    def test_a_crashing_tool_does_not_kill_the_run(self, config):
        class Exploding(Tool):
            name = "explode"
            description = "always raises"
            risk = Risk.READ_ONLY

            @property
            def input_schema(self):
                return {"type": "object", "properties": {}, "required": []}

            def run(self, **kwargs):
                raise RuntimeError("boom")

        agent = make_agent(
            config,
            [tool_message("explode", {}), text_message("recovered")],
            tools=[Exploding()],
        )
        result = agent.run("go")

        assert result.completed
        assert result.tool_calls[0].is_error
        block = [m for m in result.messages if m["role"] == "user"][1]["content"][0]
        assert block["is_error"] is True
        assert "failed unexpectedly" in block["content"]
        assert "boom" in block["content"]


class TestPermissionIntegration:
    def test_denied_call_becomes_an_error_result(self, config):
        denying = PermissionPolicy("ask", lambda tool, ti: Decision.deny("user said no"))
        agent = make_agent(
            config,
            [
                tool_message("write_file", {"path": "x.txt", "content": "hi"}),
                text_message("Understood, I won't write it."),
            ],
            policy=denying,
        )
        result = agent.run("write a file")

        assert result.completed
        assert result.tool_calls[0].allowed is False
        block = [m for m in result.messages if m["role"] == "user"][1]["content"][0]
        assert "declined" in block["content"]
        assert "user said no" in block["content"]
        assert not (config.workspace / "x.txt").exists(), "denied write must not happen"

    def test_readonly_mode_blocks_the_write_but_allows_the_read(self, workspace):
        config = Config(
            workspace=workspace, permission_mode="readonly", context_strategy="none"
        )
        calls = FakeMessage(
            content=[
                FakeToolUse("read_file", {"path": "hello.txt"}, "toolu_a"),
                FakeToolUse("write_file", {"path": "new.txt", "content": "x"}, "toolu_b"),
            ],
            stop_reason="tool_use",
        )
        agent = make_agent(config, [calls, text_message("done")], policy=build_policy("readonly"))
        result = agent.run("go")

        by_name = {c.name: c for c in result.tool_calls}
        assert by_name["read_file"].allowed
        assert not by_name["write_file"].allowed
        assert not (workspace / "new.txt").exists()

    def test_approver_is_asked_once_per_call_serially(self, config):
        seen = []

        def approver(tool, tool_input):
            seen.append(tool_input.get("path"))
            return Decision.allow()

        calls = FakeMessage(
            content=[
                FakeToolUse("write_file", {"path": "a.txt", "content": "1"}, "toolu_a"),
                FakeToolUse("write_file", {"path": "b.txt", "content": "2"}, "toolu_b"),
            ],
            stop_reason="tool_use",
        )
        agent = make_agent(
            config,
            [calls, text_message("written")],
            policy=PermissionPolicy("ask", approver),
        )
        agent.run("write two files")
        assert seen == ["a.txt", "b.txt"]


class TestStopReasons:
    def test_refusal_raises_with_the_category(self, config):
        refused = FakeMessage(
            content=[FakeText("")],
            stop_reason="refusal",
            stop_details=FakeStopDetails(category="cyber"),
        )
        agent = make_agent(config, [refused])

        with pytest.raises(RefusalError) as exc:
            agent.run("do something disallowed")
        assert exc.value.category == "cyber"

    def test_truncated_tool_call_is_refused_not_executed(self, config):
        """A truncated tool input still parses; running it acts on half a call."""
        truncated = FakeMessage(
            content=[FakeToolUse("write_file", {"path": "x.txt", "content": "partial"})],
            stop_reason="max_tokens",
        )
        agent = make_agent(config, [truncated])

        with pytest.raises(LoopError, match="truncated mid-tool-call"):
            agent.run("write a huge file")
        assert not (config.workspace / "x.txt").exists()

    def test_truncated_text_stops_cleanly_without_completing(self, config):
        agent = make_agent(
            config, [FakeMessage(content=[FakeText("half an ans")], stop_reason="max_tokens")]
        )
        result = agent.run("write an essay")

        assert result.stop_reason == "max_tokens"
        assert not result.completed
        assert result.text == "half an ans"

    def test_pause_turn_resumes_the_same_turn(self, config):
        agent = make_agent(
            config,
            [
                FakeMessage(content=[FakeText("working")], stop_reason="pause_turn"),
                text_message("finished"),
            ],
        )
        result = agent.run("search the web")

        assert result.completed
        # A pause splits one logical turn across two responses, so the text of
        # both belongs to that turn.
        assert result.text == "working\nfinished"

    def test_pauses_are_counted_per_turn_not_per_run(self, config):
        """A long run that pauses occasionally and resumes fine is healthy."""
        script = []
        for i in range(8):
            script.append(FakeMessage(content=[FakeText("...")], stop_reason="pause_turn"))
            script.append(tool_message("list_dir", {"path": "."}, f"toolu_{i}"))
        script.append(text_message("done"))

        agent = Agent(
            Config(workspace=config.workspace, permission_mode="auto", max_turns=40,
                   context_strategy="none"),
            backend=ScriptedBackend(script),
        )
        result = agent.run("a long run with occasional pauses")

        assert result.completed
        assert result.text == "done"

    def test_endless_pause_turn_is_caught(self, config):
        paused = [
            FakeMessage(content=[FakeText("...")], stop_reason="pause_turn") for _ in range(10)
        ]
        agent = Agent(
            Config(workspace=config.workspace, permission_mode="auto", max_turns=20,
                   context_strategy="none"),
            backend=ScriptedBackend(paused),
        )
        with pytest.raises(LoopError, match="without completing"):
            agent.run("go")


class TestBudgets:
    def test_turn_ceiling_stops_the_run(self, workspace):
        config = Config(
            workspace=workspace, permission_mode="auto", max_turns=3, context_strategy="none"
        )
        # Always asks for another tool call, never finishes on its own.
        responses = [tool_message("list_dir", {"path": "."}) for _ in range(10)]
        agent = make_agent(config, responses)
        result = agent.run("loop forever")

        assert result.stop_reason == "max_turns"
        assert not result.completed
        assert result.usage.turns == 3

    def test_cost_ceiling_aborts(self, workspace):
        config = Config(
            workspace=workspace,
            permission_mode="auto",
            max_cost_usd=0.001,
            context_strategy="none",
        )
        expensive = FakeMessage(
            content=[FakeText("...")],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=1_000_000, output_tokens=1_000_000),
        )
        agent = make_agent(config, [expensive, text_message("done")])

        with pytest.raises(BudgetExceededError, match="exceeded"):
            agent.run("something costly")


class TestAppendOnlyTranscript:
    def test_history_only_grows_and_earlier_turns_are_never_rewritten(self, config):
        """Editing a past turn invalidates the thinking blocks bound to it."""
        agent = make_agent(
            config,
            [
                tool_message("read_file", {"path": "hello.txt"}, "toolu_a"),
                tool_message("list_dir", {"path": "."}, "toolu_b"),
                text_message("all done"),
            ],
        )
        result = agent.run("explore")
        backend = agent.backend

        snapshots = [r["messages"] for r in backend.requests]
        for earlier, later in pairwise(snapshots):
            assert len(later) > len(earlier), "history must grow"
            assert later[: len(earlier)] == earlier, "earlier turns must not change"
        assert len(result.messages) > len(snapshots[-1])

    def test_continuing_a_prior_transcript_appends_to_it(self, config):
        first = make_agent(config, [text_message("one")])
        r1 = first.run("first question")

        second = make_agent(config, [text_message("two")])
        r2 = second.run("second question", messages=r1.messages)

        assert len(r2.messages) == len(r1.messages) + 2
        assert r2.messages[: len(r1.messages)] == r1.messages


class TestRequestShape:
    def test_system_prompt_carries_a_cache_breakpoint(self, config):
        agent = make_agent(config, [text_message("hi")])
        agent.run("hello")

        system = agent.backend.requests[0]["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_system_prompt_is_byte_stable_across_turns(self, config):
        """Anything varying in the prefix invalidates the cache every request."""
        agent = make_agent(
            config,
            [tool_message("list_dir", {"path": "."}), text_message("done")],
        )
        agent.run("go")

        systems = [r["system"] for r in agent.backend.requests]
        assert all(s == systems[0] for s in systems)

    def test_tool_schemas_are_identical_every_turn(self, config):
        agent = make_agent(
            config,
            [tool_message("list_dir", {"path": "."}), text_message("done")],
        )
        agent.run("go")

        tool_sets = [r["tools"] for r in agent.backend.requests]
        assert all(t == tool_sets[0] for t in tool_sets)


class TestUsageTracking:
    def test_usage_accumulates_across_turns(self, config):
        agent = make_agent(
            config,
            [tool_message("list_dir", {"path": "."}), text_message("done")],
        )
        result = agent.run("go")

        assert result.usage.turns == 2
        assert result.usage.input_tokens == 200
        assert result.usage.output_tokens == 100
        assert len(result.usage.per_turn) == 2

    def test_summary_is_serializable(self, config):
        import json

        agent = make_agent(config, [text_message("hi")])
        summary = agent.run("hello").summary(config.model)
        assert json.loads(json.dumps(summary))["completed"] is True


def test_result_tracks_denied_calls(config):
    denying = PermissionPolicy("ask", lambda tool, ti: Decision.deny("no"))
    agent = make_agent(
        config,
        [tool_message("run_command", {"command": "ls"}), text_message("ok")],
        policy=denying,
    )
    summary = agent.run("list files").summary(config.model)
    assert summary["denied_calls"] == 1
    assert summary["tool_calls"] == 1


class TestFinalTextIsTheTerminalTurn:
    """Regression: an early preamble must not be presented as the final answer."""

    def test_a_terminal_turn_with_no_text_does_not_resurface_a_preamble(self, config):
        agent = make_agent(
            config,
            [
                FakeMessage(
                    content=[
                        FakeText("Let me check that for you."),
                        FakeToolUse("list_dir", {"path": "."}, "toolu_1"),
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(content=[], stop_reason="end_turn"),
            ],
        )
        result = agent.run("go")

        assert result.completed
        assert result.text == "", "the preamble is not the answer"

    def test_the_last_turns_text_wins_over_earlier_turns(self, config):
        agent = make_agent(
            config,
            [
                FakeMessage(
                    content=[
                        FakeText("First I'll look around."),
                        FakeToolUse("list_dir", {"path": "."}, "toolu_1"),
                    ],
                    stop_reason="tool_use",
                ),
                text_message("The directory holds two entries."),
            ],
        )
        assert agent.run("go").text == "The directory holds two entries."


class TestPartialRunSurvivesFailure:
    """A failed run is the one most worth reading back."""

    def test_truncation_carries_the_transcript_so_far(self, config):
        agent = make_agent(
            config,
            [
                tool_message("list_dir", {"path": "."}, "toolu_1"),
                FakeMessage(
                    content=[FakeToolUse("write_file", {"path": "x", "content": "y"})],
                    stop_reason="max_tokens",
                ),
            ],
        )
        with pytest.raises(LoopError) as exc:
            agent.run("go")

        partial = exc.value.partial
        assert partial is not None
        assert partial.stop_reason == "error"
        assert partial.usage.turns == 2
        assert [c.name for c in partial.tool_calls] == ["list_dir"]
        assert len(partial.messages) >= 3

    def test_budget_overrun_carries_usage(self, workspace):
        config = Config(
            workspace=workspace,
            permission_mode="auto",
            max_cost_usd=0.001,
            context_strategy="none",
        )
        expensive = FakeMessage(
            content=[FakeText("...")],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=1_000_000, output_tokens=1_000_000),
        )
        agent = make_agent(config, [expensive])

        with pytest.raises(BudgetExceededError) as exc:
            agent.run("costly")

        assert exc.value.partial is not None
        assert exc.value.partial.usage.turns == 1

    def test_refusal_carries_the_partial_run(self, config):
        refused = FakeMessage(
            content=[FakeText("")],
            stop_reason="refusal",
            stop_details=FakeStopDetails(category="cyber"),
        )
        agent = make_agent(config, [refused])

        with pytest.raises(RefusalError) as exc:
            agent.run("disallowed")

        assert exc.value.partial is not None
        assert exc.value.category == "cyber"
