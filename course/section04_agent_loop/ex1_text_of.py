"""Exercise 4.1 -- Pull the text out of a response.

Lecture: 4.3 "end_turn and tool_use: the happy path"

A response's ``content`` is a list of blocks of different types: ``text``,
``thinking``, ``tool_use`` and more. Only ``text`` blocks are the answer meant
for the user.

Write ``text_of(response)`` to join the ``.text`` of every ``text`` block, in
order, with nothing between them, and strip surrounding whitespace. Ignore
every other block type. A response with no text blocks gives ``""``.

Check a block's ``.type`` -- don't assume every block has a ``.text``.
"""

from __future__ import annotations

from typing import Any


def text_of(response: Any) -> str:
    raise NotImplementedError("Exercise 4.1: write this part")
