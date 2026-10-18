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
    raise NotImplementedError("Exercise 3.2: write this part")


def to_api_schema(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Build a strict tool definition, validating the schema first."""
    raise NotImplementedError("Exercise 3.2: write this part")
