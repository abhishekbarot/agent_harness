"""Cross-run memory: Claude's memory tool, with the storage backend here.

The context strategies in ``model.py`` manage what the model remembers *within*
a run -- clearing stale tool results, or compacting. Memory is the other half:
what survives *between* runs. The model reads and writes files under a virtual
``/memories`` directory; this module maps that onto a real directory on disk.

This is an Anthropic-defined tool (``memory_20250818``), not a custom one: the
request declares only its type and name, and the model already knows the
command set. The harness supplies the storage -- and, as with every other tool,
the confinement. A memory path is model output like any other path.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..errors import ToolError
from .base import Risk, Tool, ToolResult
from .builtin import MAX_READ_BYTES, _resolve_within, _truncate

MEMORY_ROOT = "/memories"
# Memory is read back into the context window, often at the start of every run.
# A file that outgrows this has stopped being a note.
MAX_MEMORY_FILE_BYTES = 64_000
_READ_ONLY_COMMANDS = frozenset({"view"})


class MemoryTool(Tool):
    """Backend for the ``memory_20250818`` tool, stored under ``root``."""

    name = "memory"
    description = "Persistent memory across runs, stored as files under /memories."
    risk = Risk.WRITE
    # Commands mutate shared files; two in one turn must not interleave.
    parallel_safe = False
    prompt_hint = (
        "View your /memories directory at the start of a task, and record what "
        "a future run would need (decisions, conventions, open threads) as you "
        "go. Keep memory files short and current; do not store secrets."
    )

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    @property
    def input_schema(self) -> dict[str, Any]:
        # Anthropic-defined: the API owns the schema. Present only so the
        # abstract property is satisfied; never sent.
        return {}

    def to_api_schema(self) -> dict[str, Any]:
        return {"type": "memory_20250818", "name": self.name}

    def risk_for(self, tool_input: dict[str, Any]) -> Risk:
        if tool_input.get("command") in _READ_ONLY_COMMANDS:
            return Risk.READ_ONLY
        return Risk.WRITE

    # -- dispatch ---------------------------------------------------------

    def run(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command")
        handler = {
            "view": self._view,
            "create": self._create,
            "str_replace": self._str_replace,
            "insert": self._insert,
            "delete": self._delete,
            "rename": self._rename,
        }.get(command or "")
        if handler is None:
            raise ToolError(f"unknown memory command: {command!r}")
        self.root.mkdir(parents=True, exist_ok=True)
        return handler(kwargs)

    def _resolve(self, path: Any) -> Path:
        """Map ``/memories/...`` onto the backing directory, confined to it."""
        if not isinstance(path, str) or not (
            path == MEMORY_ROOT or path.startswith(MEMORY_ROOT + "/")
        ):
            raise ToolError(f"memory paths must start with {MEMORY_ROOT}, got {path!r}")
        relative = path[len(MEMORY_ROOT):].lstrip("/") or "."
        try:
            return _resolve_within(self.root, relative)
        except ToolError as exc:
            raise ToolError(f"memory path {path!r} escapes {MEMORY_ROOT}") from exc

    # -- commands ---------------------------------------------------------

    def _view(self, args: dict[str, Any]) -> ToolResult:
        target = self._resolve(args.get("path"))
        if target.is_dir():
            entries = sorted(
                p for p in target.rglob("*")
                if not any(part.startswith(".") for part in p.relative_to(target).parts)
            )
            lines = [
                f"{p.stat().st_size if p.is_file() else '-':>8}  "
                f"{MEMORY_ROOT}/{p.relative_to(self.root).as_posix()}{'/' if p.is_dir() else ''}"
                for p in entries
            ]
            body = "\n".join(lines) or "(empty)"
            return ToolResult(f"Contents of {args['path']}:\n{body}")
        if not target.exists():
            raise ToolError(f"{args['path']} does not exist")

        text = _read_text(target)
        lines = text.splitlines()
        start, end = 1, len(lines)
        view_range = args.get("view_range")
        if view_range is not None:
            if (
                not isinstance(view_range, list)
                or len(view_range) != 2
                or not all(isinstance(n, int) and not isinstance(n, bool) for n in view_range)
            ):
                raise ToolError("view_range must be [start_line, end_line]")
            start = max(1, view_range[0])
            end = len(lines) if view_range[1] == -1 else min(view_range[1], len(lines))
        numbered = "\n".join(
            f"{i:>6}\t{lines[i - 1]}" for i in range(start, end + 1)
        )
        return ToolResult(_truncate(numbered) or "(empty file)")

    def _create(self, args: dict[str, Any]) -> ToolResult:
        target = self._resolve(args.get("path"))
        text = args.get("file_text")
        if not isinstance(text, str):
            raise ToolError("file_text must be a string")
        if target == self.root or target.is_dir():
            raise ToolError(f"{args['path']} is a directory")
        _check_size(text)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return ToolResult(f"File created successfully at {args['path']}")

    def _str_replace(self, args: dict[str, Any]) -> ToolResult:
        target = self._existing_file(args.get("path"))
        old, new = args.get("old_str"), args.get("new_str")
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ToolError("old_str must be a non-empty string and new_str a string")
        text = _read_text(target)
        count = text.count(old)
        if count != 1:
            raise ToolError(
                f"old_str must occur exactly once in {args['path']}; found {count}"
            )
        updated = text.replace(old, new, 1)
        _check_size(updated)
        target.write_text(updated, encoding="utf-8")
        return ToolResult(f"The memory file {args['path']} has been edited.")

    def _insert(self, args: dict[str, Any]) -> ToolResult:
        target = self._existing_file(args.get("path"))
        line, insert = args.get("insert_line"), args.get("insert_text")
        if isinstance(line, bool) or not isinstance(line, int) or not isinstance(insert, str):
            raise ToolError("insert_line must be an integer and insert_text a string")
        lines = _read_text(target).splitlines(keepends=True)
        if not 0 <= line <= len(lines):
            raise ToolError(f"insert_line must be between 0 and {len(lines)}")
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        block = insert if insert.endswith("\n") else insert + "\n"
        updated = "".join(lines[:line]) + block + "".join(lines[line:])
        _check_size(updated)
        target.write_text(updated, encoding="utf-8")
        return ToolResult(f"Text inserted at line {line} of {args['path']}.")

    def _delete(self, args: dict[str, Any]) -> ToolResult:
        target = self._resolve(args.get("path"))
        if target == self.root:
            raise ToolError(f"refusing to delete {MEMORY_ROOT} itself")
        if not target.exists():
            raise ToolError(f"{args['path']} does not exist")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return ToolResult(f"Deleted {args['path']}")

    def _rename(self, args: dict[str, Any]) -> ToolResult:
        source = self._resolve(args.get("old_path"))
        dest = self._resolve(args.get("new_path"))
        if source == self.root:
            raise ToolError(f"refusing to rename {MEMORY_ROOT} itself")
        if not source.exists():
            raise ToolError(f"{args['old_path']} does not exist")
        if dest.exists():
            raise ToolError(f"{args['new_path']} already exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)
        return ToolResult(f"Renamed {args['old_path']} to {args['new_path']}")

    def _existing_file(self, path: Any) -> Path:
        target = self._resolve(path)
        if not target.is_file():
            raise ToolError(f"{path} is not an existing memory file")
        return target


def _read_text(target: Path) -> str:
    if target.stat().st_size > MAX_READ_BYTES:
        raise ToolError(f"{target.name} is over the {MAX_READ_BYTES}-byte read limit")
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"{target.name} is not valid UTF-8 text") from exc


def _check_size(text: str) -> None:
    size = len(text.encode("utf-8"))
    if size > MAX_MEMORY_FILE_BYTES:
        raise ToolError(
            f"memory file would be {size} bytes, over the {MAX_MEMORY_FILE_BYTES}-byte "
            "limit; summarize it instead of appending"
        )
