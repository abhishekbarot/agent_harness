#!/usr/bin/env python3
"""Run the eval suite.

    python evals/run_eval.py                          # every case
    python evals/run_eval.py --tag safety             # one slice
    python evals/run_eval.py --case write-a-file      # one case
    python evals/run_eval.py --json report.json       # machine-readable output

This makes real API calls and costs real money. The per-case and total cost is
printed at the end of every run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_harness.config import Config  # noqa: E402
from agent_harness.evals import load_cases, run_suite  # noqa: E402
from agent_harness.logging_setup import configure  # noqa: E402

DEFAULT_CASES = Path(__file__).parent / "cases.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the agent-harness eval suite.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--tag", help="Only run cases carrying this tag.")
    parser.add_argument("--case", help="Only run this case id.")
    parser.add_argument("--model", help="Override the model under test.")
    parser.add_argument("--effort", help="Override the effort level.")
    parser.add_argument("--json", type=Path, help="Write the report as JSON here.")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    configure(level=args.log_level, fmt="text")

    cases = load_cases(args.cases)
    if args.tag:
        cases = [c for c in cases if args.tag in c.tags]
    if args.case:
        cases = [c for c in cases if c.id == args.case]
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 2

    overrides = {k: v for k, v in {"model": args.model, "effort": args.effort}.items() if v}
    config = Config.from_env(**overrides)

    report = run_suite(cases, config)
    print(report.render())

    if args.json:
        args.json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"\nreport written to {args.json}")

    return 0 if report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
