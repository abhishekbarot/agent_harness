"""Planning: the model's plan, made explicit and visible to the harness.

Adaptive thinking already lets the model plan privately, turn by turn. What it
does not give the harness is a plan it can *see*: something to render to the
user, persist with the transcript, and grade in an eval. ``update_plan`` is that
surface -- the model writes the whole plan each time it changes, and the harness
keeps the latest version.

It touches no disk and has no side effects outside the run, so it sits at the
read-only tier and never needs approval. The plan lives in tool results inside
the transcript, never in the system prompt: editing the prompt per turn would
invalidate the prompt cache on every request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import ToolError
from .base import Risk, Tool, ToolResult

PLAN_STATUSES = ("pending", "in_progress", "completed")
MAX_PLAN_STEPS = 30
_MARKS = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}


@dataclass(frozen=True)
class PlanStep:
    step: str
    status: str

    def render(self) -> str:
        return f"{_MARKS[self.status]} {self.step}"


class UpdatePlanTool(Tool):
    name = "update_plan"
    description = (
        "Record or revise your plan for a multi-step task. Send the complete "
        "plan every time -- it replaces the previous one. Mark exactly one step "
        "in_progress while you work on it, and mark steps completed as soon as "
        "they are verified. Skip this for tasks that take one or two steps."
    )
    risk = Risk.READ_ONLY
    # The plan is shared state; two updates in one turn would race.
    parallel_safe = False
    prompt_hint = (
        "For tasks with three or more steps, keep a plan with update_plan and "
        "revise it when what you learn changes the approach."
    )

    def __init__(self) -> None:
        self.steps: list[PlanStep] = []
        self.revisions = 0

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "The full plan, in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string", "description": "What to do."},
                            "status": {"type": "string", "enum": list(PLAN_STATUSES)},
                        },
                        "required": ["step", "status"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["steps"],
        }

    def run(self, **kwargs: Any) -> ToolResult:
        raw = kwargs.get("steps")
        if not isinstance(raw, list) or not raw:
            raise ToolError("steps must be a non-empty list")
        if len(raw) > MAX_PLAN_STEPS:
            raise ToolError(f"a plan has at most {MAX_PLAN_STEPS} steps; group related work")

        steps: list[PlanStep] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ToolError("each step must be an object with 'step' and 'status'")
            text, status = item.get("step"), item.get("status")
            if not isinstance(text, str) or not text.strip():
                raise ToolError("each step needs a non-empty 'step' description")
            if status not in PLAN_STATUSES:
                raise ToolError(f"status must be one of {PLAN_STATUSES}, got {status!r}")
            steps.append(PlanStep(text.strip(), status))

        in_progress = sum(1 for s in steps if s.status == "in_progress")
        if in_progress > 1:
            raise ToolError("only one step may be in_progress at a time")

        self.steps = steps
        self.revisions += 1
        done = sum(1 for s in steps if s.status == "completed")
        rendered = "\n".join(s.render() for s in steps)
        return ToolResult(
            content=f"Plan updated ({done}/{len(steps)} completed):\n{rendered}",
            metadata={"revision": self.revisions, "completed": done, "total": len(steps)},
        )
