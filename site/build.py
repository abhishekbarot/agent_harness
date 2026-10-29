#!/usr/bin/env python3
"""Assemble the published site: the pages, the course files the workspace runs,
and the pytest wheels. Used by the Pages workflow and by the browser checks.

    python site/build.py _site

The reference solutions are never copied. This script is the one place that
decides what goes public, and it refuses to finish if a solution slipped in.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
COURSE = SITE.parent / "course"

PAGES = [
    "index.html", "workspace.html",
    "tokens.css", "styles.css", "workspace.css",
    "theme.js", "config.js", "curriculum.js", "app.js",
    "store.js", "runner.js", "runner-worker.js", "workspace.js",
    "social.png",
]
# What the in-browser grader loads: shared helpers, stubs and tests.
COURSE_FILES = ["conftest.py", "loader.py", "common/*.py", "section*/ex*.py", "section*/test_*.py"]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: build.py OUT_DIR", file=sys.stderr)
        return 2
    out = Path(argv[1]).resolve()
    # Never build into site/ itself, where rmtree would delete the sources.
    if out == SITE or (SITE in out.parents and out.name != "_site"):
        print(f"refusing to build into {out}", file=sys.stderr)
        return 2
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for name in PAGES:
        shutil.copy2(SITE / name, out / name)

    if subprocess.call([sys.executable, str(SITE / "fetch_wheels.py")]) != 0:
        return 1
    shutil.copytree(SITE / "vendor" / "py", out / "vendor" / "py")

    for pattern in COURSE_FILES:
        for src in sorted(COURSE.glob(pattern)):
            dest = out / "course" / src.relative_to(COURSE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    leaked = [
        p for p in (out / "course").rglob("*")
        if "solutions" in p.parts or "BEGIN SOLUTION" in _text(p)
    ]
    if leaked:
        print(f"error: solutions would be published: {leaked}", file=sys.stderr)
        return 1

    (out / ".nojekyll").touch()
    files = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"built {out} ({files} files)")
    return 0


def _text(path: Path) -> str:
    if not path.is_file() or path.suffix != ".py":
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
