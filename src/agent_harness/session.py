"""Transcript persistence.

A run that cannot be replayed cannot be debugged. The transcript is the full
append-only message list plus the usage and tool-call record, written as JSON so
an eval or a postmortem can read it back.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logging_setup import get_logger

log = get_logger("session")


def to_jsonable(value: Any) -> Any:
    """Convert SDK content blocks (Pydantic models) into plain JSON structures."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    # SDK models expose to_dict(); Pydantic v2 exposes model_dump().
    for method in ("to_dict", "model_dump"):
        fn = getattr(value, method, None)
        if callable(fn):
            try:
                return to_jsonable(fn())
            except Exception:  # noqa: BLE001 - fall through to the repr below
                pass
    if hasattr(value, "__dict__"):
        return {k: to_jsonable(v) for k, v in vars(value).items() if not k.startswith("_")}
    return repr(value)


def save_transcript(result: Any, directory: Path, model: str, prompt: str) -> Path:
    """Write a run to ``<directory>/run-<timestamp>.json`` and return the path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"run-{stamp}.json"

    payload = {
        "timestamp": stamp,
        "model": model,
        "prompt": prompt,
        "summary": result.summary(model),
        "tool_calls": [asdict(c) for c in result.tool_calls],
        "messages": to_jsonable(result.messages),
        "final_text": result.text,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.info("transcript saved", extra={"path": str(path)})
    return path
