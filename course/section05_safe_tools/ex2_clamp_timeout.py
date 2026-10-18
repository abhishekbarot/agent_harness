"""Exercise 5.2 -- Validate and cap a model-supplied timeout.

Lecture: 5.6 "Timeouts: validating and capping values the model supplies"

A shell tool lets the model pick a timeout. Without limits, one call could run
for hours -- longer than every budget the harness has.

Write ``clamp_timeout(raw, default=120, maximum=600)``:

* ``None`` means "use the default" -> return ``default``
* anything that is not an ``int`` -> raise ``ToolError``. Watch out:
  ``True`` is an ``int`` in Python, and must be rejected too
* zero or negative -> raise ``ToolError``
* otherwise return ``raw``, capped at ``maximum``
"""

from __future__ import annotations

from typing import Any

from common.harness import ToolError


def clamp_timeout(raw: Any, default: int = 120, maximum: int = 600) -> int:
    raise NotImplementedError("Exercise 5.2: write this part")
