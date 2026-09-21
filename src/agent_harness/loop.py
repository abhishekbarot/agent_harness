"""The agent loop: the harness proper.

This is a manual loop rather than the SDK's ``tool_runner`` helper, because the
loop *is* the subject here -- every decision it makes is one a harness has to
make somewhere:

  * which ``stop_reason`` means "done" vs. "keep going" vs. "stop, something is
    wrong";
  * what happens to a tool call the user refuses;
  * how tool results are batched back into the transcript;
  * what counts as running out of budget.

The transcript is strictly append-only. Turns are added, never edited or
removed. That is a correctness requirement, not a style preference: thinking
blocks are bound to the history that produced them, and rewriting an earlier
turn invalidates them. Trimming context is the *server's* job here, via the
context-management strategy in ``model.py``.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .errors import (
    BudgetExceededError,
    HarnessError,
    LoopError,
    RefusalError,
    ToolError,
)
from .logging_setup import get_logger
from .model import DEFAULT_INSTRUCTIONS, AnthropicBackend, ModelBackend, build_system_prompt
from .permissions import PermissionPolicy, build_policy
from .tools.base import Tool, ToolRegistry, ToolResult
from .tools.builtin import default_tools
from .usage import Usage

log = get_logger("loop")

MAX_PAUSE_RESUMES = 5


@dataclass
class ToolCallRecord:
    """One tool call, as it actually happened. Feeds logs, evals, and tests."""

    name: str
    input: dict[str, Any]
    allowed: bool
    is_error: bool
    duration_ms: float
    result_preview: str = ""


@dataclass
class RunResult:
    """The outcome of a run."""

    text: str
    stop_reason: str
    messages: list[dict[str, Any]]
    usage: Usage
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def completed(self) -> bool:
        """True when the model finished on its own terms."""
        return self.stop_reason == "end_turn"

    def summary(self, model: str) -> dict[str, Any]:
        return {
            "stop_reason": self.stop_reason,
            "completed": self.completed,
            "tool_calls": len(self.tool_calls),
            "denied_calls": sum(1 for c in self.tool_calls if not c.allowed),
            "duration_s": round(self.duration_s, 2),
            **self.usage.summary(model),
        }


class Agent:
    """Runs a task to completion, or to a clean stop."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        backend: ModelBackend | None = None,
        tools: list[Tool] | None = None,
        policy: PermissionPolicy | None = None,
        instructions: str = DEFAULT_INSTRUCTIONS,
    ) -> None:
        self.config = config or Config()
        self.registry = ToolRegistry(
            tools if tools is not None else default_tools(
                self.config.workspace, self.config.denied_commands
            )
        )
        self.policy = policy or build_policy(self.config.permission_mode)
        self.backend = backend or AnthropicBackend(self.config)
        self.system = build_system_prompt(instructions, str(self.config.workspace))

    # -- the loop ---------------------------------------------------------

    def run(self, prompt: str, messages: list[dict[str, Any]] | None = None) -> RunResult:
        """Run until the model stops calling tools, or a ceiling is hit.

        Pass ``messages`` to continue an existing transcript; the new prompt is
        appended to it.

        On a ``HarnessError`` the exception carries a ``partial`` RunResult with
        everything that happened up to the failure -- the runs most worth
        replaying are the ones that did not finish.
        """
        started = time.monotonic()
        history: list[dict[str, Any]] = list(messages or [])
        history.append({"role": "user", "content": prompt})

        usage = Usage()
        calls: list[ToolCallRecord] = []
        stop_reason = "max_turns"
        final_text = ""
        # Text accumulated for the turn in progress. A turn can span several
        # responses when a server-side tool pauses it.
        pending_text = ""
        # Pauses are counted within a turn, not across the run: a long run that
        # pauses occasionally and resumes cleanly each time is healthy.
        pause_resumes = 0

        def snapshot(reason: str) -> RunResult:
            return RunResult(
                text=final_text,
                stop_reason=reason,
                messages=history,
                usage=usage,
                tool_calls=calls,
                duration_s=time.monotonic() - started,
            )

        log.info(
            "run started",
            extra={
                "model": self.config.model,
                "effort": self.config.effort,
                "tools": len(self.registry),
                "permission_mode": self.config.permission_mode,
            },
        )

        try:
            for turn in range(1, self.config.max_turns + 1):
                response = self.backend.create(
                    messages=history,
                    system=self.system,
                    tools=self.registry.to_api_schemas(),
                )
                usage.add(getattr(response, "usage", None))
                self._check_budget(usage)

                # Append the assistant turn verbatim, including thinking and
                # tool_use blocks. Storing only the text would drop the blocks
                # the API needs to continue the conversation.
                history.append({"role": "assistant", "content": response.content})

                reason = getattr(response, "stop_reason", None) or "end_turn"
                text = _text_of(response)
                pending_text = f"{pending_text}\n{text}".strip() if pending_text else text

                log.debug(
                    "turn complete",
                    extra={"turn": turn, "stop_reason": reason, "chars": len(text)},
                )

                if reason == "refusal":
                    details = getattr(response, "stop_details", None)
                    category = getattr(details, "category", None)
                    raise RefusalError(
                        f"the model declined this request (category: {category})", category
                    )

                if reason == "pause_turn":
                    # A server-side tool hit its iteration limit mid-turn. The
                    # turn is already appended, so re-sending resumes it.
                    pause_resumes += 1
                    if pause_resumes >= MAX_PAUSE_RESUMES:
                        raise LoopError(
                            f"a single turn paused {pause_resumes} times without "
                            "completing; giving up"
                        )
                    continue

                # The turn finished, however many responses it took.
                final_text = pending_text
                pending_text = ""
                pause_resumes = 0

                tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]

                if reason == "max_tokens":
                    # A truncated tool input still parses as a plausible object,
                    # so running it would act on arguments the model never
                    # finished writing.
                    if tool_uses:
                        raise LoopError(
                            "the response was truncated mid-tool-call; raise max_tokens "
                            f"(currently {self.config.max_tokens}) and retry"
                        )
                    stop_reason = "max_tokens"
                    break

                if not tool_uses:
                    stop_reason = reason
                    break

                results = self._dispatch(tool_uses, calls)
                # Every result for a turn goes back in ONE user message.
                # Splitting them teaches the model to stop batching its calls.
                history.append({"role": "user", "content": results})
            else:
                log.warning(
                    "run hit the turn ceiling", extra={"max_turns": self.config.max_turns}
                )
        except HarnessError as exc:
            exc.partial = snapshot("error")
            log.warning(
                "run failed", extra={"error": type(exc).__name__, "turns": usage.turns}
            )
            raise

        result = snapshot(stop_reason)
        log.info("run finished", extra=result.summary(self.config.model))
        return result

    # -- tool dispatch ----------------------------------------------------

    def _dispatch(
        self, tool_uses: list[Any], calls: list[ToolCallRecord]
    ) -> list[dict[str, Any]]:
        """Gate, then execute, every tool call in one assistant turn.

        Permission checks run serially and first -- an interactive approver must
        not be asked two questions at once. Execution can then fan out, but only
        when every approved tool is parallel-safe.
        """
        approved: list[tuple[Any, Tool]] = []
        blocked: dict[str, ToolResult] = {}

        for block in tool_uses:
            tool = self.registry.get(block.name)
            if tool is None:
                blocked[block.id] = ToolResult(
                    content=(
                        f"Unknown tool {block.name!r}. Available tools: "
                        f"{', '.join(t.name for t in self.registry)}."
                    ),
                    is_error=True,
                )
                calls.append(ToolCallRecord(block.name, {}, False, True, 0.0, "unknown tool"))
                continue

            tool_input = block.input if isinstance(block.input, dict) else {}
            if not isinstance(block.input, dict):
                blocked[block.id] = ToolResult(
                    content="Tool input was not a JSON object; re-issue the call.",
                    is_error=True,
                )
                calls.append(ToolCallRecord(block.name, {}, False, True, 0.0, "malformed input"))
                continue

            decision = self.policy.check(tool, tool_input)
            if not decision.allowed:
                blocked[block.id] = ToolResult(
                    content=f"The user declined this tool call. Reason: {decision.reason}",
                    is_error=True,
                )
                calls.append(
                    ToolCallRecord(block.name, tool_input, False, True, 0.0, decision.reason)
                )
                continue

            approved.append((block, tool))

        executed: dict[str, ToolResult] = {}
        can_parallelize = len(approved) > 1 and all(t.parallel_safe for _, t in approved)

        if can_parallelize:
            with ThreadPoolExecutor(max_workers=min(len(approved), 8)) as pool:
                futures = {
                    block.id: pool.submit(self._execute, tool, block.input, calls)
                    for block, tool in approved
                }
                for block_id, future in futures.items():
                    executed[block_id] = future.result()
        else:
            for block, tool in approved:
                executed[block.id] = self._execute(tool, block.input, calls)

        # Rebuild in the model's original order; a result must exist for every
        # tool_use id or the API rejects the next request.
        return [
            (blocked.get(b.id) or executed[b.id]).to_block(b.id)
            for b in tool_uses
        ]

    def _execute(
        self, tool: Tool, tool_input: dict[str, Any], calls: list[ToolCallRecord]
    ) -> ToolResult:
        started = time.monotonic()
        try:
            result = tool.run(**tool_input)
        except ToolError as exc:
            # Expected, recoverable failure: hand it to the model, don't abort.
            result = ToolResult(content=f"Error: {exc}", is_error=True)
        except Exception as exc:  # noqa: BLE001 - a tool bug must not kill the run
            log.exception("tool raised an unexpected exception", extra={"tool": tool.name})
            result = ToolResult(
                content=f"Error: {tool.name} failed unexpectedly: {exc!r}", is_error=True
            )

        duration_ms = (time.monotonic() - started) * 1000
        calls.append(
            ToolCallRecord(
                name=tool.name,
                input=tool_input,
                allowed=True,
                is_error=result.is_error,
                duration_ms=duration_ms,
                result_preview=result.content[:200],
            )
        )
        log.info(
            "tool call",
            extra={
                "tool": tool.name,
                "is_error": result.is_error,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return result

    # -- budgets ----------------------------------------------------------

    def _check_budget(self, usage: Usage) -> None:
        limit = self.config.max_cost_usd
        if limit is None:
            return
        spent = usage.cost_usd(self.config.model)
        if spent is not None and spent > limit:
            raise BudgetExceededError(
                f"run cost ${spent:.4f} exceeded the ${limit:.2f} ceiling after "
                f"{usage.turns} turns"
            )


def _text_of(response: Any) -> str:
    """Concatenate the text blocks of a response, ignoring thinking and tool_use."""
    return "".join(
        block.text
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text"
    ).strip()
