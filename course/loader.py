"""Loads your exercise files -- or the reference solutions -- by name.

Tests never import exercise files directly. They call ``load(__file__, name)``,
which finds the file in the same section folder as the test. Setting
``COURSE_SOLUTIONS=1`` points the same tests at ``solutions/`` instead, which
is how the course itself is checked.

The section folder is put on ``sys.path``, so a later exercise can import an
earlier one (``from ex1_resolve_within import resolve_within``) and build on
your own code.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

COURSE_ROOT = Path(__file__).resolve().parent


def using_solutions() -> bool:
    return os.environ.get("COURSE_SOLUTIONS", "").lower() in ("1", "true", "yes")


def load(test_file: str, name: str) -> ModuleType:
    section = Path(test_file).resolve().parent.name
    base = COURSE_ROOT / "solutions" if using_solutions() else COURSE_ROOT
    section_dir = str(base / section)
    if section_dir not in sys.path:
        sys.path.insert(0, section_dir)
    return importlib.import_module(name)
