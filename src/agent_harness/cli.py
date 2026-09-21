"""Command line entry point.

    agent-harness "refactor the parser and run the tests"
    agent-harness --permission-mode auto --workspace ./sandbox "add a CHANGELOG"
    echo "summarize this repo" | agent-harness -
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import VALID_CONTEXT_STRATEGIES, VALID_EFFORTS, VALID_PERMISSION_MODES, Config
from .errors import HarnessError
from .logging_setup import configure
from .loop import Agent
from .session import save_transcript


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-harness",
        description="Run an agent loop against the Claude API.",
    )
    parser.add_argument("prompt", help="The task for the agent. Use '-' to read from stdin.")
    parser.add_argument("--model", help="Model id (default: claude-opus-5).")
    parser.add_argument("--effort", choices=VALID_EFFORTS, help="Thinking/token effort level.")
    parser.add_argument("--max-tokens", type=int, help="Max output tokens per turn.")
    parser.add_argument("--max-turns", type=int, help="Ceiling on loop iterations.")
    parser.add_argument("--max-cost", type=float, help="Abort once estimated cost exceeds this.")
    parser.add_argument(
        "--workspace", type=Path, help="Directory tools may touch (default: cwd)."
    )
    parser.add_argument(
        "--permission-mode",
        choices=VALID_PERMISSION_MODES,
        help="auto | ask | readonly | deny (default: ask).",
    )
    parser.add_argument(
        "--context-strategy",
        choices=VALID_CONTEXT_STRATEGIES,
        help="Server-side context management (default: clear_tool_uses).",
    )
    parser.add_argument("--transcript-dir", type=Path, help="Write a JSON transcript here.")
    parser.add_argument("--log-format", choices=("text", "json"), help="Log output format.")
    parser.add_argument("--log-level", help="DEBUG | INFO | WARNING | ERROR.")
    parser.add_argument(
        "--quiet", action="store_true", help="Print only the final answer on stdout."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    overrides = {
        key: value
        for key, value in {
            "model": args.model,
            "effort": args.effort,
            "max_tokens": args.max_tokens,
            "max_turns": args.max_turns,
            "max_cost_usd": args.max_cost,
            "workspace": args.workspace,
            "permission_mode": args.permission_mode,
            "context_strategy": args.context_strategy,
            "transcript_dir": args.transcript_dir,
            "log_format": args.log_format,
            "log_level": args.log_level.upper() if args.log_level else None,
        }.items()
        if value is not None
    }

    try:
        config = Config.from_env(**overrides)
    except HarnessError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    configure(
        level="ERROR" if args.quiet else config.log_level,
        fmt=config.log_format,
    )

    prompt = (sys.stdin.read() if args.prompt == "-" else args.prompt).strip()
    if not prompt:
        print("error: empty prompt", file=sys.stderr)
        return 2

    try:
        agent = Agent(config)
        result = agent.run(prompt)
    except HarnessError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        # A failed run is the one most worth reading back, so persist whatever
        # the loop got through before it raised.
        if config.transcript_dir and exc.partial is not None:
            path = save_transcript(exc.partial, config.transcript_dir, config.model, prompt)
            print(f"partial transcript: {path}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    print(result.text)

    if config.transcript_dir:
        save_transcript(result, config.transcript_dir, config.model, prompt)

    if not args.quiet:
        summary = result.summary(config.model)
        cost = summary.get("cost_usd")
        print(
            f"\n[{summary['stop_reason']} | {summary['turns']} turns | "
            f"{summary['tool_calls']} tool calls | {summary['total_tokens']} tokens"
            + (f" | ${cost:.4f}" if isinstance(cost, float) else "")
            + f" | {summary['duration_s']}s]",
            file=sys.stderr,
        )

    return 0 if result.completed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
