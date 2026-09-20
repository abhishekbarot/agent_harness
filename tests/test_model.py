"""Request shape.

What the harness actually sends is a contract: adaptive thinking (not a token
budget), effort inside output_config, a cache breakpoint on the system prefix,
and the right beta paired with the right context-management edit.
"""

from __future__ import annotations

import pytest

from agent_harness.config import Config
from agent_harness.model import AnthropicBackend, build_system_prompt
from conftest import FakeMessage, FakeText


class RecordingStream:
    def __init__(self, params):
        self.params = params

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(())

    def get_final_message(self):
        return FakeMessage(content=[FakeText("ok")])


class RecordingClient:
    """Stands in for anthropic.Anthropic, capturing calls to both endpoints."""

    def __init__(self):
        self.calls = []
        outer = self

        class Messages:
            def stream(self, **params):
                outer.calls.append(("stable", params))
                return RecordingStream(params)

        class BetaMessages:
            def stream(self, **params):
                outer.calls.append(("beta", params))
                return RecordingStream(params)

        self.messages = Messages()
        self.beta = type("Beta", (), {"messages": BetaMessages()})()


def backend(**kwargs):
    config = Config(**{"context_strategy": "none", **kwargs})
    client = RecordingClient()
    return AnthropicBackend(config, client=client), client


def send(bk, tools=None):
    return bk.create(
        messages=[{"role": "user", "content": "hi"}],
        system=build_system_prompt("be careful", "/tmp/ws"),
        tools=tools if tools is not None else [],
    )


class TestRequestParameters:
    def test_thinking_is_adaptive_with_no_token_budget(self):
        bk, client = backend()
        send(bk)
        params = client.calls[0][1]

        assert params["thinking"]["type"] == "adaptive"
        # budget_tokens is rejected outright on this model family.
        assert "budget_tokens" not in params["thinking"]

    def test_effort_sits_inside_output_config(self):
        bk, client = backend(effort="max")
        send(bk)
        params = client.calls[0][1]

        assert params["output_config"] == {"effort": "max"}
        assert "effort" not in params  # not a top-level parameter

    def test_conversation_tail_is_auto_cached(self):
        bk, client = backend()
        send(bk)
        assert client.calls[0][1]["cache_control"] == {"type": "ephemeral"}

    def test_model_and_max_tokens_are_passed_through(self):
        bk, client = backend(model="claude-sonnet-5", max_tokens=4096)
        send(bk)
        params = client.calls[0][1]

        assert params["model"] == "claude-sonnet-5"
        assert params["max_tokens"] == 4096

    def test_tools_are_omitted_when_there_are_none(self):
        bk, client = backend()
        send(bk, tools=[])
        assert "tools" not in client.calls[0][1]

    def test_tools_are_included_when_present(self):
        bk, client = backend()
        send(bk, tools=[{"name": "t", "description": "d", "input_schema": {}}])
        assert len(client.calls[0][1]["tools"]) == 1


class TestContextStrategies:
    def test_none_uses_the_stable_endpoint(self):
        bk, client = backend(context_strategy="none")
        send(bk)
        endpoint, params = client.calls[0]

        assert endpoint == "stable"
        assert "betas" not in params
        assert "context_management" not in params

    def test_clear_tool_uses_pairs_its_own_beta(self):
        bk, client = backend(context_strategy="clear_tool_uses")
        send(bk)
        endpoint, params = client.calls[0]

        assert endpoint == "beta"
        assert params["betas"] == ["context-management-2025-06-27"]
        assert params["context_management"] == {
            "edits": [{"type": "clear_tool_uses_20250919"}]
        }

    def test_compact_pairs_its_own_beta(self):
        bk, client = backend(context_strategy="compact")
        send(bk)
        endpoint, params = client.calls[0]

        assert endpoint == "beta"
        assert params["betas"] == ["compact-2026-01-12"]
        assert params["context_management"] == {"edits": [{"type": "compact_20260112"}]}

    @pytest.mark.parametrize("strategy", ["clear_tool_uses", "compact"])
    def test_the_two_strategies_are_never_mixed(self, strategy):
        """They are separate features; sending both betas is not a supported shape."""
        bk, client = backend(context_strategy=strategy)
        send(bk)
        assert len(client.calls[0][1]["betas"]) == 1


class TestSystemPrompt:
    def test_carries_exactly_one_cache_breakpoint(self):
        blocks = build_system_prompt("instructions", "/tmp/ws")
        assert len(blocks) == 1
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_mentions_the_workspace_and_the_instructions(self):
        text = build_system_prompt("BE CAREFUL", "/tmp/my-ws")[0]["text"]
        assert "BE CAREFUL" in text
        assert "/tmp/my-ws" in text

    def test_is_deterministic(self):
        """Any variation here invalidates the cache on every single request."""
        a = build_system_prompt("x", "/ws")
        b = build_system_prompt("x", "/ws")
        assert a == b


def test_stream_is_drained_before_the_final_message_is_read():
    bk, client = backend()
    message = send(bk)
    assert message.content[0].text == "ok"
