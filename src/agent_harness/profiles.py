"""Profiles: who the agent is for this run.

A profile (or persona) is the role, standards, and boundaries an agent works
to, carried in the system prompt. Changing the profile changes the agent's
behavior without touching the loop or the tools -- a reviewer and an engineer
can share every line of the harness and differ only here.

A profile is resolved once at startup and then frozen into the cached system
prefix. Swapping it mid-run would invalidate the cache on every request.
"""

from __future__ import annotations

from pathlib import Path

from .errors import ConfigError

BUILTIN_PROFILES: dict[str, str] = {
    "engineer": (
        "You are a careful software engineering agent. You work in small, verifiable "
        "steps and you check your work with the tools available to you."
    ),
    "reviewer": (
        "You are a code reviewer. Read the relevant code, then report concrete "
        "defects -- each with the file, the line, and the input that triggers it -- "
        "ranked by severity. Do not edit files; your output is the review."
    ),
    "explainer": (
        "You are a guide to an unfamiliar codebase. Read before you answer, cite "
        "the files and functions you are describing, and say plainly when the "
        "code does not show something."
    ),
}
DEFAULT_PROFILE = "engineer"
# A profile is instructions, not a document dump. Reference material belongs in
# the workspace, where the model can read it on demand.
MAX_PROFILE_CHARS = 20_000


def load_profile(spec: str) -> str:
    """Resolve a built-in profile name, or a path to a text/Markdown file."""
    if spec in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[spec]

    path = Path(spec).expanduser()
    if not path.is_file():
        raise ConfigError(
            f"unknown profile {spec!r}: not one of {sorted(BUILTIN_PROFILES)} "
            "and not a readable file"
        )
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"could not read profile {spec!r}: {exc}") from exc
    if not text:
        raise ConfigError(f"profile {spec!r} is empty")
    if len(text) > MAX_PROFILE_CHARS:
        raise ConfigError(
            f"profile {spec!r} is {len(text)} characters, over the "
            f"{MAX_PROFILE_CHARS}-character limit"
        )
    return text
