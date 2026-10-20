"""Shared pytest setup for the course exercises.

Run one section:   pytest course/section03_tool_use
Run everything:    pytest course
Check solutions:   COURSE_SOLUTIONS=1 pytest course   (instructors only)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `common` and `loader` importable from every test file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
