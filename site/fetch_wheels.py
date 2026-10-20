#!/usr/bin/env python3
"""Download the pytest wheels the workspace runs in the browser.

The workspace grades exercises with the course's real pytest suites, running
inside Pyodide (Python compiled to WebAssembly). Pyodide's own package index
lives on a CDN; serving these few pure-Python wheels from the site instead means
the grader only depends on the CDN for Pyodide itself.

Versions match what Pyodide 0.26.4 (Python 3.12) ships. Every file is checked
against its PyPI sha256, so a swapped or corrupted download fails loudly.

    python site/fetch_wheels.py      # writes site/vendor/py/*.whl
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "vendor" / "py"

WHEELS = [
    (
        "pytest-8.1.1-py3-none-any.whl",
        "2a8386cfc11fa9d2c50ee7b2a57e7d898ef90470a7a34c4b949ff59662bb78b7",
        "https://files.pythonhosted.org/packages/4d/7e/c79cecfdb6aa85c6c2e3cf63afc56d0f165f24f5c66c03c695c4d9b84756/pytest-8.1.1-py3-none-any.whl",
    ),
    (
        "pluggy-1.5.0-py3-none-any.whl",
        "44e1ad92c8ca002de6377e165f3e0f1be63266ab4d554740532335b9d75ea669",
        "https://files.pythonhosted.org/packages/88/5f/e351af9a41f866ac3f1fac4ca0613908d9a41741cfcf2228f4ad853b697d/pluggy-1.5.0-py3-none-any.whl",
    ),
    (
        "iniconfig-2.0.0-py3-none-any.whl",
        "b6a85871a79d2e3b22d2d1b94ac2824226a63c6b741c88f7ae975f18b6778374",
        "https://files.pythonhosted.org/packages/ef/a6/62565a6e1cf69e10f5727360368e451d4b7f58beeac6173dc9db836a5b46/iniconfig-2.0.0-py3-none-any.whl",
    ),
    (
        "packaging-23.2-py3-none-any.whl",
        "8c491190033a9af7e1d931d0b5dacc2ef47509b34dd0de67ed209b5203fc88c7",
        "https://files.pythonhosted.org/packages/ec/1a/610693ac4ee14fcdf2d9bf3c493370e4f2ef7ae2e19217d7a237ff42367d/packaging-23.2-py3-none-any.whl",
    ),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, sha256, url in WHEELS:
        target = OUT / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
            print(f"ok      {name}")
            continue
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha256:
            print(f"error: {name} has sha256 {digest}, expected {sha256}", file=sys.stderr)
            return 1
        target.write_bytes(data)
        print(f"fetched {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
