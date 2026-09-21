"""Exception hierarchy for the harness.

These are harness-level failures. Anthropic SDK exceptions (``anthropic.RateLimitError``
and friends) are deliberately *not* wrapped -- callers that want to distinguish
retryable from non-retryable API failures should catch the SDK's own typed classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime
    from .loop import RunResult


class HarnessError(Exception):
    """Base class for every error raised by the harness itself.

    ``partial`` carries the run as it stood when the failure happened, when the
    error was raised from inside the agent loop. A failed run is usually the
    one you most want to read back, so the transcript must survive the raise.
    """

    partial: RunResult | None = None

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.partial = None


class ConfigError(HarnessError):
    """Configuration is missing or internally inconsistent."""


class ToolError(HarnessError):
    """A tool failed in a way the model should see and can recover from.

    Raised inside a tool's ``run``; the loop converts it into a ``tool_result``
    with ``is_error: True`` rather than aborting the run.
    """


class ToolNotFoundError(ToolError):
    """The model called a tool that is not in the registry."""


class PermissionDeniedError(ToolError):
    """A tool call was refused by the permission policy or the approver."""


class BudgetExceededError(HarnessError):
    """The run hit its turn, token, or cost ceiling."""


class LoopError(HarnessError):
    """The agent loop cannot make progress (truncation, malformed tool input)."""


class RefusalError(HarnessError):
    """The model declined the request (``stop_reason == "refusal"``)."""

    def __init__(self, message: str, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category
