"""agent_harness -- the loop around the model.

An agent is a model in a loop with tools. The harness is everything around that
loop: the tool surface, the permission gate, context management, budgets,
observability, and the evals that tell you whether a change helped.
"""

from .config import Config
from .errors import (
    BudgetExceededError,
    ConfigError,
    HarnessError,
    LoopError,
    PermissionDeniedError,
    RefusalError,
    ToolError,
)
from .loop import Agent, RunResult, ToolCallRecord
from .permissions import Decision, PermissionPolicy, auto_approve, build_policy
from .tools import Risk, Tool, ToolRegistry, ToolResult, default_tools
from .usage import Usage

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "BudgetExceededError",
    "Config",
    "ConfigError",
    "Decision",
    "HarnessError",
    "LoopError",
    "PermissionDeniedError",
    "PermissionPolicy",
    "RefusalError",
    "Risk",
    "RunResult",
    "Tool",
    "ToolCallRecord",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "Usage",
    "__version__",
    "auto_approve",
    "build_policy",
    "default_tools",
]
