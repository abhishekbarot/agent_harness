"""The eval loop.

A harness without evals is a harness you change by vibes. Each case sets up a
throwaway workspace, runs the agent against it, and grades the *outcome* -- the
files on disk, the tools actually called, the text produced -- rather than
matching the model's wording.

Cases run in ``auto`` permission mode: an unattended run must never block on an
approval prompt nobody is there to answer.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .errors import HarnessError
from .logging_setup import get_logger
from .loop import Agent, RunResult
from .usage import Usage

log = get_logger("evals")

# A grader takes the run and its workspace and returns (passed, explanation).
Grader = Callable[[RunResult, Path, dict[str, Any]], "tuple[bool, str]"]


# -- graders --------------------------------------------------------------


def _completed(result: RunResult, workspace: Path, spec: dict[str, Any]):
    return result.completed, f"stop_reason={result.stop_reason}"


def _tool_called(result: RunResult, workspace: Path, spec: dict[str, Any]):
    name = spec["name"]
    called = [c.name for c in result.tool_calls if c.allowed]
    return name in called, f"called={called}"


def _tool_not_called(result: RunResult, workspace: Path, spec: dict[str, Any]):
    name = spec["name"]
    called = [c.name for c in result.tool_calls if c.allowed]
    return name not in called, f"called={called}"


def _max_tool_calls(result: RunResult, workspace: Path, spec: dict[str, Any]):
    limit = int(spec["count"])
    actual = len(result.tool_calls)
    return actual <= limit, f"{actual} calls, limit {limit}"


def _no_denied(result: RunResult, workspace: Path, spec: dict[str, Any]):
    denied = [c.name for c in result.tool_calls if not c.allowed]
    return not denied, f"denied={denied}"


def _no_tool_errors(result: RunResult, workspace: Path, spec: dict[str, Any]):
    failed = [c.name for c in result.tool_calls if c.is_error]
    return not failed, f"errored={failed}"


def _text_matches(result: RunResult, workspace: Path, spec: dict[str, Any]):
    pattern = spec["pattern"]
    hit = re.search(pattern, result.text) is not None
    return hit, f"pattern={pattern!r} text={result.text[:120]!r}"


def _file_exists(result: RunResult, workspace: Path, spec: dict[str, Any]):
    target = workspace / spec["path"]
    return target.exists(), f"{spec['path']} {'exists' if target.exists() else 'missing'}"


def _file_contains(result: RunResult, workspace: Path, spec: dict[str, Any]):
    target = workspace / spec["path"]
    if not target.exists():
        return False, f"{spec['path']} does not exist"
    body = target.read_text(encoding="utf-8", errors="replace")
    needle = spec["text"]
    return needle in body, f"{needle!r} {'found' if needle in body else 'not found'}"


def _file_unchanged(result: RunResult, workspace: Path, spec: dict[str, Any]):
    """Guards against collateral damage -- the agent editing what it was not asked to."""
    target = workspace / spec["path"]
    if not target.exists():
        return False, f"{spec['path']} was deleted"
    body = target.read_text(encoding="utf-8", errors="replace")
    same = body == spec["text"]
    return same, f"{spec['path']} {'unchanged' if same else 'modified'}"


GRADERS: dict[str, Grader] = {
    "completed": _completed,
    "tool_called": _tool_called,
    "tool_not_called": _tool_not_called,
    "max_tool_calls": _max_tool_calls,
    "no_denied": _no_denied,
    "no_tool_errors": _no_tool_errors,
    "text_matches": _text_matches,
    "file_exists": _file_exists,
    "file_contains": _file_contains,
    "file_unchanged": _file_unchanged,
}


# -- cases ----------------------------------------------------------------


@dataclass
class EvalCase:
    id: str
    prompt: str
    files: dict[str, str] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    permission_mode: str = "auto"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EvalCase:
        missing = {"id", "prompt"} - raw.keys()
        if missing:
            raise ValueError(f"eval case is missing required keys: {sorted(missing)}")
        unknown = {c.get("type") for c in raw.get("checks", [])} - GRADERS.keys()
        if unknown:
            raise ValueError(f"case {raw['id']!r} uses unknown check types: {sorted(unknown)}")
        return cls(
            id=raw["id"],
            prompt=raw["prompt"],
            files=raw.get("files", {}),
            checks=raw.get("checks", []),
            tags=raw.get("tags", []),
            permission_mode=raw.get("permission_mode", "auto"),
        )


@dataclass
class CheckResult:
    type: str
    passed: bool
    detail: str


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None
    usage: Usage = field(default_factory=Usage)
    duration_s: float = 0.0
    tool_calls: int = 0

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


@dataclass
class EvalReport:
    results: list[CaseResult]
    model: str

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def total_cost_usd(self) -> float:
        return sum(r.usage.cost_usd(self.model) or 0.0 for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "passed": self.passed,
            "total": self.total,
            "pass_rate": round(self.pass_rate, 4),
            "total_cost_usd": round(self.total_cost_usd(), 6),
            "cases": [
                {
                    "id": r.case_id,
                    "passed": r.passed,
                    "error": r.error,
                    "tool_calls": r.tool_calls,
                    "duration_s": round(r.duration_s, 2),
                    "cost_usd": r.usage.cost_usd(self.model),
                    "failed_checks": [
                        {"type": c.type, "detail": c.detail} for c in r.failures
                    ],
                }
                for r in self.results
            ],
        }

    def render(self) -> str:
        lines = [f"\n{'=' * 64}", f"eval report -- {self.model}", "=" * 64]
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            lines.append(f"[{mark}] {r.case_id}  ({r.tool_calls} tool calls, {r.duration_s:.1f}s)")
            if r.error:
                lines.append(f"         error: {r.error}")
            for check in r.failures:
                lines.append(f"         x {check.type}: {check.detail}")
        cost = self.total_cost_usd()
        lines.append("-" * 64)
        lines.append(
            f"{self.passed}/{self.total} passed ({self.pass_rate:.0%})"
            + (f" -- ${cost:.4f}" if cost else "")
        )
        return "\n".join(lines)


# -- runner ---------------------------------------------------------------


def load_cases(path: Path) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = raw["cases"] if isinstance(raw, dict) else raw
    return [EvalCase.from_dict(c) for c in cases]


def run_case(
    case: EvalCase,
    config: Config,
    agent_factory: Callable[[Config], Agent] | None = None,
) -> CaseResult:
    """Run one case in a throwaway workspace and grade the outcome."""
    workspace = Path(tempfile.mkdtemp(prefix=f"eval-{case.id}-"))
    try:
        # Everything here can fail on malformed case data or a transport error.
        # A suite run costs real money, so one bad case is recorded and the rest
        # still run -- discarding results already paid for helps nobody.
        # KeyboardInterrupt is a BaseException and still aborts the suite.
        try:
            for rel, content in case.files.items():
                target = workspace / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            case_config = Config(
                **{
                    **{
                        f.name: getattr(config, f.name)
                        for f in config.__dataclass_fields__.values()
                    },
                    "workspace": workspace,
                    "permission_mode": case.permission_mode,
                }
            )
            agent = (agent_factory or Agent)(case_config)
            result = agent.run(case.prompt)
        except HarnessError as exc:
            partial = getattr(exc, "partial", None)
            return CaseResult(
                case.id,
                passed=False,
                error=f"{type(exc).__name__}: {exc}",
                usage=partial.usage if partial else Usage(),
                tool_calls=len(partial.tool_calls) if partial else 0,
            )
        except Exception as exc:  # noqa: BLE001 - keep the suite alive
            log.exception("eval case raised", extra={"case": case.id})
            return CaseResult(case.id, passed=False, error=f"{type(exc).__name__}: {exc}")

        checks = []
        for spec in case.checks:
            passed, detail = GRADERS[spec["type"]](result, workspace, spec)
            checks.append(CheckResult(spec["type"], passed, detail))

        return CaseResult(
            case_id=case.id,
            passed=all(c.passed for c in checks),
            checks=checks,
            usage=result.usage,
            duration_s=result.duration_s,
            tool_calls=len(result.tool_calls),
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_suite(
    cases: list[EvalCase],
    config: Config,
    agent_factory: Callable[[Config], Agent] | None = None,
) -> EvalReport:
    results = []
    for case in cases:
        log.info("running eval case", extra={"case": case.id})
        results.append(run_case(case, config, agent_factory))
    return EvalReport(results, config.model)
