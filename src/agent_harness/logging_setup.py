"""Structured logging.

Text for humans at a terminal, line-delimited JSON for log aggregators. Both go
through the stdlib ``logging`` module so SDK logs (``ANTHROPIC_LOG=debug``) land
in the same stream.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

LOGGER_NAME = "agent_harness"

# Attributes present on every LogRecord; anything else was passed via `extra`
# and belongs in the structured payload.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with ``extra`` fields promoted to top level."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure(level: str = "INFO", fmt: str = "text") -> logging.Logger:
    """Configure and return the harness logger. Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", datefmt="%H:%M:%S")
        )
    logger.addHandler(handler)
    # The harness owns its own stream; don't duplicate into the root handler.
    logger.propagate = False
    return logger


def get_logger(suffix: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}" if suffix else LOGGER_NAME)
