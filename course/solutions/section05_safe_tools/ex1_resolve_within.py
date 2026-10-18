"""Exercise 5.1 -- Keep every path inside the workspace.

Lecture: 5.4 "Path confinement: ../, absolute paths and symlinks"

Tool arguments are written by the model, so treat them like input from a
stranger. A JSON Schema can say ``path`` is a string; it cannot say the path
stays inside your project.

Write ``resolve_within(root, candidate)``:

* ``candidate`` must be a non-empty string (not just whitespace) -- otherwise
  raise ``ToolError`` with a message containing ``"non-empty"``
* join it to ``root`` and **resolve** it -- resolving collapses ``..`` and
  follows symlinks, so all three escapes are caught by one check:
  ``../secret``, ``/etc/passwd``, and a symlink inside the workspace that
  points outside it
* if the result is neither ``root`` itself nor inside ``root``, raise
  ``ToolError`` with a message containing ``"escapes"``
* otherwise return the resolved path

You can assume ``root`` is already resolved. ``Path.is_relative_to`` helps.
"""

from __future__ import annotations

from pathlib import Path

from common.harness import ToolError


def resolve_within(root: Path, candidate: str) -> Path:
    # BEGIN SOLUTION
    if not isinstance(candidate, str) or not candidate.strip():
        raise ToolError("path must be a non-empty string")
    target = (root / candidate).resolve()
    if target != root and not target.is_relative_to(root):
        raise ToolError(f"path {candidate!r} escapes the workspace root")
    return target
    # END SOLUTION
