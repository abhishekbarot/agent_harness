#!/usr/bin/env python3
"""Generate the student exercise files from the reference solutions.

Each solution marks the code students write with a pair of comment lines:

    # BEGIN SOLUTION
    ...the answer...
    # END SOLUTION

This script copies every ``solutions/<section>/ex*.py`` to ``<section>/``,
replacing each marked block with a ``NotImplementedError`` at the same
indentation. Edit the solution, then regenerate -- never edit a stub by hand.

    python course/make_stubs.py           # write the stubs
    python course/make_stubs.py --check   # fail if any stub is out of date (CI)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

COURSE = Path(__file__).resolve().parent
BEGIN = "# BEGIN SOLUTION"
END = "# END SOLUTION"


def exercise_number(path: Path) -> str:
    section = re.match(r"section(\d+)", path.parent.name)
    exercise = re.match(r"ex(\d+)_", path.name)
    if not (section and exercise):
        raise ValueError(f"cannot read an exercise number from {path}")
    return f"{int(section.group(1))}.{int(exercise.group(1))}"


def make_stub(source: str, number: str, name: str) -> str:
    out: list[str] = []
    inside = False
    for lineno, line in enumerate(source.splitlines(keepends=True), start=1):
        marker = line.strip()
        if marker == BEGIN:
            if inside:
                raise ValueError(f"{name}:{lineno}: nested {BEGIN}")
            inside = True
            indent = line[: len(line) - len(line.lstrip())]
            out.append(
                f'{indent}raise NotImplementedError("Exercise {number}: write this part")\n'
            )
        elif marker == END:
            if not inside:
                raise ValueError(f"{name}:{lineno}: {END} without {BEGIN}")
            inside = False
        elif not inside:
            out.append(line)
    if inside:
        raise ValueError(f"{name}: {BEGIN} is never closed")
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Only report stale stubs.")
    args = parser.parse_args(argv)

    stale: list[Path] = []
    for solution in sorted((COURSE / "solutions").glob("section*/ex*.py")):
        stub_path = COURSE / solution.parent.name / solution.name
        source = solution.read_text(encoding="utf-8")
        if BEGIN not in source:
            raise SystemExit(f"{solution} has no {BEGIN} block")
        stub = make_stub(source, exercise_number(solution), solution.name)
        current = stub_path.read_text(encoding="utf-8") if stub_path.exists() else None
        if current == stub:
            continue
        stale.append(stub_path)
        if not args.check:
            stub_path.parent.mkdir(parents=True, exist_ok=True)
            stub_path.write_text(stub, encoding="utf-8")

    for path in stale:
        verb = "out of date" if args.check else "wrote"
        print(f"{verb}: {path.relative_to(COURSE)}")
    if args.check and stale:
        print("run: python course/make_stubs.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
