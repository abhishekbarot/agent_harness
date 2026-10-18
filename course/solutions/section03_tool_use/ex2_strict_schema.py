"""Exercise 3.2 -- Validate a tool schema for strict mode.

Lecture: 3.2 "JSON Schema for tool inputs, strict mode, required-but-nullable"

With ``"strict": true`` on a tool, the API guarantees the model's arguments
match your schema exactly. Strict mode has rules, and breaking them gets you a
400 error on your first live request. Catch the mistakes at startup instead.

1. ``validate_strict_schema(tool_name, schema)`` raises ``ValueError`` when:
   * ``schema["type"]`` is not ``"object"``
   * ``additionalProperties`` is not exactly ``False``
   * any property is missing from ``required`` -- in strict mode an optional
     argument is written as required-but-nullable, e.g.
     ``{"type": ["string", "null"]}``, not left out of ``required``
   * ``required`` names a property that is not declared
   Put the tool name in every error message.

2. ``to_api_schema(name, description, schema)`` returns the tool definition to
   send: ``name``, ``description``, ``"strict": True`` and ``input_schema``.
   Default ``additionalProperties`` to ``False`` when it is missing, validate,
   and do not modify the caller's dict.
"""

from __future__ import annotations

from typing import Any


def validate_strict_schema(tool_name: str, schema: dict[str, Any]) -> None:
    """Raise ``ValueError`` if ``schema`` breaks a strict-mode rule."""
    # BEGIN SOLUTION
    if schema.get("type") != "object":
        raise ValueError(f"tool {tool_name!r}: input_schema type must be 'object'")
    if schema.get("additionalProperties") is not False:
        raise ValueError(f"tool {tool_name!r}: additionalProperties must be false")
    properties = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    missing = properties - required
    if missing:
        raise ValueError(
            f"tool {tool_name!r}: {sorted(missing)} must be listed in 'required'; "
            'make optional arguments nullable instead, e.g. {"type": ["string", "null"]}'
        )
    unknown = required - properties
    if unknown:
        raise ValueError(f"tool {tool_name!r}: 'required' names undeclared {sorted(unknown)}")
    # END SOLUTION


def to_api_schema(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Build a strict tool definition, validating the schema first."""
    # BEGIN SOLUTION
    checked = dict(schema)
    checked.setdefault("additionalProperties", False)
    validate_strict_schema(name, checked)
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": checked,
    }
    # END SOLUTION
