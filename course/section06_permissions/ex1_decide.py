"""Exercise 6.1 -- The permission table.

Lectures: 6.1 "Risk tiers", 6.2 "Permission modes"

Every tool call has a risk tier, and the harness runs in a permission mode.
Together they decide what happens to the call:

============  ===========  ===========  ===========
mode          read_only    write        dangerous
============  ===========  ===========  ===========
``auto``      allow        allow        allow
``ask``       allow        ask          ask
``readonly``  allow        deny         deny
``deny``      deny         deny         deny
============  ===========  ===========  ===========

Write ``decide(mode, risk)`` returning ``"allow"``, ``"ask"`` or ``"deny"``.
Raise ``ValueError`` for a mode not in the table -- a typo in a config file
must never quietly turn into a permissive default.
"""

from __future__ import annotations

from common.harness import Risk

MODES = ("auto", "ask", "readonly", "deny")


def decide(mode: str, risk: Risk) -> str:
    raise NotImplementedError("Exercise 6.1: write this part")
