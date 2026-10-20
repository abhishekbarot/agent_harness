"""Exercise 5.4 -- A safe read_file tool.

Lecture: 5.1 "Read, list and search tools"

Combine 5.1 and 5.3 into a real tool. They are imported for you, so this runs
on your own code -- make sure 5.1 and 5.3 pass first.

Write ``read_file(root, path, max_bytes=256_000, max_chars=30_000)``:

1. Resolve ``path`` with ``resolve_within`` (escapes raise ``ToolError``).
2. Raise ``ToolError`` if the file does not exist (message contains
   ``"not found"``), is a directory (``"directory"``), is bigger than
   ``max_bytes`` (``"limit"``), or is not valid UTF-8 (``"UTF-8"``).
3. Number the lines, starting at 1, as ``f"{n:>6}\\t{line}"``, joined with
   ``"\\n"`` -- line numbers let the model point at exact lines later.
4. Return ``ToolResult`` with the numbered text passed through ``truncate``
   with ``max_chars``. An empty file returns ``"(empty file)"``.

Check the size *before* reading the file.
"""

from __future__ import annotations

from pathlib import Path

from common.harness import ToolError, ToolResult
from ex1_resolve_within import resolve_within
from ex3_truncate import truncate


def read_file(
    root: Path, path: str, max_bytes: int = 256_000, max_chars: int = 30_000
) -> ToolResult:
    # BEGIN SOLUTION
    target = resolve_within(root, path)
    if not target.exists():
        raise ToolError(f"file not found: {path}")
    if target.is_dir():
        raise ToolError(f"{path} is a directory")
    size = target.stat().st_size
    if size > max_bytes:
        raise ToolError(f"{path} is {size} bytes, over the {max_bytes}-byte limit")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"{path} is not valid UTF-8 text") from exc

    numbered = "\n".join(f"{n:>6}\t{line}" for n, line in enumerate(text.splitlines(), 1))
    return ToolResult(truncate(numbered, max_chars) or "(empty file)")
    # END SOLUTION
