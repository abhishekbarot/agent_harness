"""Exercise 5.3 -- Truncate long tool output.

Lecture: 5.5 "Truncating output so one result can't fill the context window"

A single ``cat`` of a log file can be megabytes. Everything a tool returns goes
into the model's context window -- and you pay for it on every later turn.

Write ``truncate(text, limit)``:

* text of ``limit`` characters or fewer comes back unchanged
* longer text is cut to its first ``limit`` characters, followed by a newline
  and a marker saying how much was dropped:
  ``"...[truncated N characters]"`` where N is the number removed

The marker matters: it tells the model the output is incomplete, so it can
search or read a smaller range instead of guessing.
"""

from __future__ import annotations


def truncate(text: str, limit: int) -> str:
    # BEGIN SOLUTION
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[truncated {len(text) - limit} characters]"
    # END SOLUTION
