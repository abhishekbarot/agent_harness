"""The model backend: everything that talks to the Messages API.

Kept behind a narrow protocol so the loop can be driven by a scripted fake in
tests. The loop never imports ``anthropic`` directly.

Requests stream by default. Streaming is not about showing tokens as they
arrive -- it is timeout protection. A non-streaming request with a large
``max_tokens`` can outlive the HTTP idle timeout and die with nothing to show
for it; ``.get_final_message()`` gives the same complete response either way.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .config import Config
from .logging_setup import get_logger

log = get_logger("model")

# Server-side context management. Both write to `context_management.edits`, but
# they are different features with different betas and must not be mixed.
_CONTEXT_STRATEGIES = {
    "clear_tool_uses": ("context-management-2025-06-27", {"type": "clear_tool_uses_20250919"}),
    "compact": ("compact-2026-01-12", {"type": "compact_20260112"}),
}


@runtime_checkable
class ModelBackend(Protocol):
    """One turn of the conversation: send history, get the next assistant message."""

    def create(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str | list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any: ...


class AnthropicBackend:
    """The real backend, over the Anthropic Python SDK."""

    def __init__(self, config: Config, client: Any = None) -> None:
        self.config = config
        if client is not None:
            self.client = client
        else:
            import anthropic

            # The SDK retries connection errors, 408/409/429 and 5xx on its own
            # with exponential backoff. Don't hand-roll a second retry layer on
            # top -- wall-clock becomes timeout x (max_retries + 1).
            self.client = anthropic.Anthropic(
                timeout=config.request_timeout,
                max_retries=config.max_retries,
            )

    def _request_params(
        self,
        messages: list[dict[str, Any]],
        system: str | list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system,
            "messages": messages,
            "output_config": {"effort": self.config.effort},
            # Adaptive thinking: the model decides depth per turn and interleaves
            # reasoning between tool calls. There is no token budget to tune --
            # `budget_tokens` is rejected outright on this model family.
            "thinking": {"type": "adaptive", "display": self.config.thinking_display},
            # Automatic caching for the conversation tail. The static system
            # prefix carries its own explicit breakpoint (see prompt.py).
            "cache_control": {"type": "ephemeral"},
        }
        if tools:
            params["tools"] = tools
        return params

    def create(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str | list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        params = self._request_params(messages, system, tools)
        strategy = _CONTEXT_STRATEGIES.get(self.config.context_strategy)

        if strategy is None:
            stream_ctx = self.client.messages.stream(**params)
        else:
            beta, edit = strategy
            stream_ctx = self.client.beta.messages.stream(
                **params,
                betas=[beta],
                context_management={"edits": [edit]},
            )

        with stream_ctx as stream:
            # Drain the stream; the SDK accumulates the message for us.
            for _ in stream:
                pass
            return stream.get_final_message()


def build_system_prompt(instructions: str, workspace: str) -> list[dict[str, Any]]:
    """Build the system prompt as a single cacheable block.

    The explicit ``cache_control`` breakpoint here is what makes the prefix
    reusable across turns. Keep this text byte-stable for the whole run:
    interpolating a timestamp, a UUID, or anything else that varies invalidates
    the cache on every single request and the hit rate silently sits at zero.
    """
    text = (
        f"{instructions}\n\n"
        f"You are operating inside the workspace at {workspace}.\n"
        "All file paths you pass to tools must stay inside that workspace.\n\n"
        "Guidelines:\n"
        "- Read a file before you edit it.\n"
        "- Prefer search_files over reading many files one at a time.\n"
        "- Tool calls that write or run commands may be refused by the user; if a "
        "call is refused, do not retry it verbatim -- explain what you need, or "
        "propose a different approach.\n"
        "- When the task is complete, say so plainly and stop calling tools."
    )
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


DEFAULT_INSTRUCTIONS = (
    "You are a careful software engineering agent. You work in small, verifiable "
    "steps and you check your work with the tools available to you."
)
