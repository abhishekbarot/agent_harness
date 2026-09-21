"""Built-in tools: filesystem reads, writes, search, and shell.

Every path argument is model output, so it is untrusted. Each tool resolves the
path and confines it to the workspace root before touching the disk. Resolving
first matters: it collapses ``..`` and follows symlinks, so a symlink pointing
outside the workspace is caught by the same check.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from ..errors import ToolError
from .base import Risk, Tool, ToolResult

# Guardrails that keep a single tool result from blowing out the context window.
MAX_READ_BYTES = 256_000
MAX_OUTPUT_CHARS = 30_000
MAX_SEARCH_MATCHES = 200
COMMAND_TIMEOUT_SECONDS = 120
# A ceiling on the model-supplied timeout. Without one, a single tool call can
# outlive every turn and cost ceiling the harness has.
MAX_COMMAND_TIMEOUT_SECONDS = 600


def _resolve_within(root: Path, candidate: str) -> Path:
    """Resolve ``candidate`` against ``root`` and reject anything that escapes.

    Schema validation does not check this -- a schema says ``path`` is a string,
    not that it stays inside the workspace.
    """
    if not isinstance(candidate, str) or not candidate.strip():
        raise ToolError("path must be a non-empty string")
    target = (root / candidate).resolve()
    if target != root and not target.is_relative_to(root):
        raise ToolError(
            f"path {candidate!r} escapes the workspace root; "
            "paths must stay inside the configured workspace"
        )
    return target


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n... [truncated {omitted} characters]"


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read a UTF-8 text file from the workspace. Returns the file contents with "
        "1-indexed line numbers. Use this before editing a file."
    )
    risk = Risk.READ_ONLY

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, relative to the workspace root.",
                }
            },
            "required": ["path"],
        }

    def run(self, **kwargs: Any) -> ToolResult:
        target = _resolve_within(self.root, kwargs.get("path", ""))
        if not target.exists():
            raise ToolError(f"file not found: {kwargs['path']}")
        if target.is_dir():
            raise ToolError(f"{kwargs['path']} is a directory; use list_dir")
        if target.stat().st_size > MAX_READ_BYTES:
            raise ToolError(
                f"file is {target.stat().st_size} bytes, over the "
                f"{MAX_READ_BYTES}-byte read limit"
            )
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"{kwargs['path']} is not valid UTF-8 text") from exc

        numbered = "\n".join(
            f"{i:>6}\t{line}" for i, line in enumerate(text.splitlines(), start=1)
        )
        return ToolResult(
            content=_truncate(numbered) or "(empty file)",
            metadata={"path": str(target), "bytes": target.stat().st_size},
        )


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Write UTF-8 text to a file in the workspace, creating parent directories "
        "as needed. Overwrites the file if it already exists."
    )
    risk = Risk.WRITE
    parallel_safe = False

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to write, relative to the workspace root.",
                },
                "content": {"type": "string", "description": "Full file contents to write."},
            },
            "required": ["path", "content"],
        }

    def run(self, **kwargs: Any) -> ToolResult:
        content = kwargs.get("content")
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        target = _resolve_within(self.root, kwargs.get("path", ""))
        if target.is_dir():
            raise ToolError(f"{kwargs['path']} is a directory")

        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        verb = "Overwrote" if existed else "Created"
        return ToolResult(
            content=f"{verb} {kwargs['path']} ({len(content)} characters).",
            metadata={"path": str(target), "created": not existed},
        )


class ListDirTool(Tool):
    name = "list_dir"
    description = "List the entries of a directory in the workspace, one per line."
    risk = Risk.READ_ONLY

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": ["string", "null"],
                    "description": "Directory path relative to the workspace root. "
                    "Pass null for the root itself.",
                }
            },
            "required": ["path"],
        }

    def run(self, **kwargs: Any) -> ToolResult:
        target = _resolve_within(self.root, kwargs.get("path") or ".")
        if not target.exists():
            raise ToolError(f"directory not found: {kwargs.get('path', '.')}")
        if not target.is_dir():
            raise ToolError(f"{kwargs.get('path')} is not a directory")

        entries = []
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
            if entry.name.startswith("."):
                continue
            entries.append(f"{entry.name}/" if entry.is_dir() else entry.name)
        return ToolResult(
            content="\n".join(entries) or "(empty directory)",
            metadata={"path": str(target), "count": len(entries)},
        )


class SearchFilesTool(Tool):
    name = "search_files"
    description = (
        "Search workspace files for a regular expression. Returns matching lines as "
        "path:line:text. Prefer this over reading many files."
    )
    risk = Risk.READ_ONLY

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python regular expression."},
                "glob": {
                    "type": ["string", "null"],
                    "description": "Glob restricting which files are searched, e.g. '**/*.py'. "
                    "Pass null to search all files.",
                },
            },
            "required": ["pattern", "glob"],
        }

    def run(self, **kwargs: Any) -> ToolResult:
        pattern = kwargs.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ToolError("pattern must be a non-empty string")
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ToolError(f"invalid regular expression: {exc}") from exc

        matches: list[str] = []
        for path in sorted(self.root.glob(kwargs.get("glob") or "**/*")):
            if len(matches) >= MAX_SEARCH_MATCHES:
                break
            if not path.is_file():
                continue
            # Skip dotfiles by their path *relative to the workspace*. Testing
            # the absolute path would skip everything whenever the workspace
            # itself sits under a dot-directory (~/.agent/project).
            if any(part.startswith(".") for part in path.relative_to(self.root).parts):
                continue
            # A glob can still reach outside the root via a symlinked directory.
            if not path.resolve().is_relative_to(self.root):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = path.relative_to(self.root)
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{rel}:{lineno}:{line.strip()[:200]}")
                    if len(matches) >= MAX_SEARCH_MATCHES:
                        break

        if not matches:
            return ToolResult(content=f"No matches for {pattern!r}.", metadata={"count": 0})
        return ToolResult(content=_truncate("\n".join(matches)), metadata={"count": len(matches)})


class RunCommandTool(Tool):
    """Shell access. The broadest tool, and the one the policy guards hardest."""

    name = "run_command"
    description = (
        "Run a shell command in the workspace and return its stdout and stderr. "
        "Use for builds, tests, and version control."
    )
    risk = Risk.DANGEROUS
    parallel_safe = False

    def __init__(self, root: Path, denied: tuple[str, ...] = ()) -> None:
        self.root = root
        self.denied = denied

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "timeout": {
                    "type": ["integer", "null"],
                    "description": f"Seconds before the command is killed "
                    f"(default {COMMAND_TIMEOUT_SECONDS}, max "
                    f"{MAX_COMMAND_TIMEOUT_SECONDS}). Pass null for the default.",
                },
            },
            "required": ["command", "timeout"],
        }

    def run(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ToolError("command must be a non-empty string")

        # A hard denylist that applies in every permission mode, including `auto`.
        # It is a backstop against catastrophic commands, not a security boundary:
        # real isolation needs a container.
        lowered = command.lower()
        for pattern in self.denied:
            if pattern.lower() in lowered:
                raise ToolError(f"command blocked by policy (matched {pattern!r})")

        timeout = _clamp_timeout(kwargs.get("timeout"))
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=int(timeout),
                env={**os.environ, "GIT_PAGER": "cat", "PAGER": "cat"},
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"command timed out after {timeout}s") from exc

        parts = []
        if proc.stdout:
            parts.append(proc.stdout.rstrip())
        if proc.stderr:
            parts.append(f"[stderr]\n{proc.stderr.rstrip()}")
        body = "\n".join(parts) or "(no output)"
        # A non-zero exit is reported as an error result so the model can react,
        # but it is not a harness failure.
        return ToolResult(
            content=_truncate(f"exit code: {proc.returncode}\n{body}"),
            is_error=proc.returncode != 0,
            metadata={"exit_code": proc.returncode, "command": command},
        )


def _clamp_timeout(raw: Any) -> int:
    """Validate and bound a model-supplied timeout.

    ``None`` means "use the default". Anything else must be a positive integer,
    and is capped so one tool call cannot outlive the whole run.
    """
    if raw is None:
        return COMMAND_TIMEOUT_SECONDS
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ToolError("timeout must be an integer number of seconds, or null")
    if raw <= 0:
        raise ToolError("timeout must be greater than zero")
    return min(raw, MAX_COMMAND_TIMEOUT_SECONDS)


def default_tools(root: Path, denied_commands: tuple[str, ...] = ()) -> list[Tool]:
    """The standard tool set, in a fixed order so the cached prefix stays stable."""
    return [
        ReadFileTool(root),
        ListDirTool(root),
        SearchFilesTool(root),
        WriteFileTool(root),
        RunCommandTool(root, denied_commands),
    ]
