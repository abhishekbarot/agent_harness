from __future__ import annotations

import json
import logging

from agent_harness.logging_setup import JsonFormatter, configure


def record(**extra):
    rec = logging.LogRecord("agent_harness", logging.INFO, __file__, 1, "hello", None, None)
    for key, value in extra.items():
        setattr(rec, key, value)
    return rec


def test_json_formatter_emits_one_object_per_line():
    line = JsonFormatter().format(record())
    payload = json.loads(line)
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert "\n" not in line


def test_extra_fields_are_promoted_to_top_level():
    payload = json.loads(JsonFormatter().format(record(tool="read_file", duration_ms=12.5)))
    assert payload["tool"] == "read_file"
    assert payload["duration_ms"] == 12.5


def test_non_serializable_extras_do_not_raise():
    payload = json.loads(JsonFormatter().format(record(obj=object())))
    assert isinstance(payload["obj"], str)


def test_configure_is_idempotent():
    first = configure(fmt="json")
    second = configure(fmt="json")
    assert first is second
    assert len(second.handlers) == 1  # not stacked on repeat calls
