"""Harness configuration.

One frozen dataclass, built from defaults + environment. Frozen matters: the
system prompt and tool list feed the cached request prefix, so anything that
mutates them mid-run silently invalidates the prompt cache.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

DEFAULT_MODEL = "claude-opus-5"
VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
VALID_PERMISSION_MODES = ("auto", "ask", "readonly", "deny")
# Server-side context management strategies. "clear_tool_uses" drops stale tool
# results outright; "compact" summarizes earlier context when the window fills.
VALID_CONTEXT_STRATEGIES = ("none", "clear_tool_uses", "compact")


@dataclass(frozen=True)
class Config:
    """Everything the harness needs to run, resolved once at startup."""

    model: str = DEFAULT_MODEL
    max_tokens: int = 16_000
    effort: str = "high"

    # Ceilings. The loop stops cleanly when it crosses one of these.
    max_turns: int = 25
    max_cost_usd: float | None = None

    # Where tools are allowed to touch the filesystem.
    workspace: Path = field(default_factory=Path.cwd)

    permission_mode: str = "ask"
    # Shell commands the bash tool will never run, whatever the mode.
    denied_commands: tuple[str, ...] = ("rm -rf /", "mkfs", "dd if=", ":(){", "shutdown", "reboot")

    # Server-side context management (beta). "none" runs on the plain,
    # non-beta Messages endpoint.
    context_strategy: str = "clear_tool_uses"

    # Adaptive thinking. "summarized" surfaces reasoning; the API default is
    # "omitted", which streams thinking blocks with empty text.
    thinking_display: str = "summarized"

    request_timeout: float = 600.0
    max_retries: int = 3

    log_level: str = "INFO"
    log_format: str = "text"  # "text" | "json"
    transcript_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.effort not in VALID_EFFORTS:
            raise ConfigError(f"effort must be one of {VALID_EFFORTS}, got {self.effort!r}")
        if self.permission_mode not in VALID_PERMISSION_MODES:
            raise ConfigError(
                f"permission_mode must be one of {VALID_PERMISSION_MODES}, "
                f"got {self.permission_mode!r}"
            )
        if self.max_turns < 1:
            raise ConfigError("max_turns must be >= 1")
        if self.max_tokens < 1:
            raise ConfigError("max_tokens must be >= 1")
        if self.context_strategy not in VALID_CONTEXT_STRATEGIES:
            raise ConfigError(
                f"context_strategy must be one of {VALID_CONTEXT_STRATEGIES}, "
                f"got {self.context_strategy!r}"
            )
        if self.max_cost_usd is not None and self.max_cost_usd <= 0:
            raise ConfigError("max_cost_usd must be positive when set")
        if self.log_format not in ("text", "json"):
            raise ConfigError(f"log_format must be 'text' or 'json', got {self.log_format!r}")
        # Resolve the workspace once so every path check compares real paths.
        object.__setattr__(self, "workspace", Path(self.workspace).resolve())

    @classmethod
    def from_env(cls, **overrides: object) -> Config:
        """Build a config from ``AGENT_*`` environment variables.

        Explicit ``overrides`` win over the environment, which wins over defaults.
        """
        env: dict[str, object] = {}
        if v := os.getenv("AGENT_MODEL"):
            env["model"] = v
        if v := os.getenv("AGENT_EFFORT"):
            env["effort"] = v
        if v := os.getenv("AGENT_MAX_TOKENS"):
            env["max_tokens"] = _int(v, "AGENT_MAX_TOKENS")
        if v := os.getenv("AGENT_MAX_TURNS"):
            env["max_turns"] = _int(v, "AGENT_MAX_TURNS")
        if v := os.getenv("AGENT_MAX_COST_USD"):
            env["max_cost_usd"] = _float(v, "AGENT_MAX_COST_USD")
        if v := os.getenv("AGENT_WORKSPACE"):
            env["workspace"] = Path(v)
        if v := os.getenv("AGENT_PERMISSION_MODE"):
            env["permission_mode"] = v
        if v := os.getenv("AGENT_CONTEXT_STRATEGY"):
            env["context_strategy"] = v
        if v := os.getenv("AGENT_THINKING_DISPLAY"):
            env["thinking_display"] = v
        if v := os.getenv("AGENT_LOG_LEVEL"):
            env["log_level"] = v.upper()
        if v := os.getenv("AGENT_LOG_FORMAT"):
            env["log_format"] = v.lower()
        if v := os.getenv("AGENT_TRANSCRIPT_DIR"):
            env["transcript_dir"] = Path(v)
        env.update(overrides)
        return cls(**env)  # type: ignore[arg-type]


def _int(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc


def _float(value: str, name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {value!r}") from exc

