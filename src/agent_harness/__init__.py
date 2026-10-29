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
from .profiles import BUILTIN_PROFILES, load_profile
from .tools import (
    MemoryTool,
    PlanStep,
    Risk,
    Tool,
    ToolRegistry,
    ToolResult,
    UpdatePlanTool,
    default_tools,
)
from .usage import Usage

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "BUILTIN_PROFILES",
    "BudgetExceededError",
    "Config",
    "ConfigError",
    "Decision",
    "HarnessError",
    "LoopError",
    "MemoryTool",
    "PermissionDeniedError",
    "PermissionPolicy",
    "PlanStep",
    "RefusalError",
    "Risk",
    "RunResult",
    "Tool",
    "ToolCallRecord",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "UpdatePlanTool",
    "Usage",
    "__version__",
    "auto_approve",
    "build_policy",
    "default_tools",
    "load_profile",
]
